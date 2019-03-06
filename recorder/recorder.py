#!/usr/bin/env python3
'''
 * Copyright (c) 2019 Rudy Baraglia & Yazid Benazzouz for Linagora.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
'''

import os
import time
from threading import Thread

import json
import numpy as np
from queue import Queue
import cv2
import pyaudio
import wave
import argparse
import paho.mqtt.client as mqtt
import tenacity


FILE_PATH = os.path.dirname(os.path.abspath(__file__))
XMAP_FILE = os.path.join(FILE_PATH, "xmap_thetaS_1280x640.pgm")
YMAP_FILE = os.path.join(FILE_PATH, "ymap_thetaS_1280x640.pgm")

SUPPORTED_INPUT = (1280,720)
DEFAULT_CAMERA_INDEX = 0
DEFAULT_SAMPLE_RATE = 16000


def main():
    client = RecorderClient()
    client.run()

class RecorderClient:
    def __init__(self):
        with open(os.path.join(FILE_PATH, 'config.json'), 'r') as f:
            self.broker_info = json.load(f)
        try:
            self.v_recorder = VideoRecorder(DEFAULT_CAMERA_INDEX)
        except IOError:
            print("Failed to create instance of video recorder")
            self.v_recorder = None
        self.a_recorder = AudioRecorder(DEFAULT_SAMPLE_RATE,1)

        self.mqttClient = self._broker_connect()
        if self.mqttClient is None:
            print("Could not connect to broker.")
            exit(-1)
            
        self.recording = False

    def run(self):
        try:
            self.mqttClient.loop_forever()
        except KeyboardInterrupt:
            print("Process interrupted by user")
        finally:
            self.recording = False
            print("Recorder is off.")

    def start_recording(self, vfilepath, afilepath):
        if self.recording:
            self.stop_recording()
        self.recording = True
        if self.v_recorder is None or not self.v_recorder.is_ready():
            try:
                self.v_recorder = VideoRecorder(0)
            except IOError:
                self.v_recorder = None
                print("Failed to create instance of video recorder")
            else:
                self.v_recorder = VideoRecorder(0)
        else:
            self.v_recorder.start_recording(vfilepath)
        self.a_recorder.start_recording(afilepath)
        self.publish_status()
    
    def stop_recording(self):
        if self.recording:
            if self.v_recorder is not None:
                self.v_recorder.stop_recording()
            self.a_recorder.stop_recording()
            self.publish_status()
            self.recording = False
    
    @tenacity.retry(wait=tenacity.wait_random(min=1, max=10),
                retry=tenacity.retry_if_result(lambda s: s is None),
                retry_error_callback=(lambda s: s.result())
                )
    def _broker_connect(self):
        """Tries to connect to MQTT broker until it succeeds"""
        print("Attempting connexion to broker at {}:{}".format(self.broker_info['broker_ip'], self.broker_info['broker_port']))
        try:
            broker = mqtt.Client()
            broker.on_connect = self._on_broker_connect
            broker.connect(self.broker_info['broker_ip'], self.broker_info['broker_port'], 0)
            return broker
        except:
            print("Failed to connect to broker (Auto-retry)")
            return None

    def publish_status(self):
        print("recorder is {}recording".format('not ' if not self.recording else ''))
        payload = json.dumps({"recording":self.recording})
        self.mqttClient.publish("recorder/status", payload)

    def _on_broker_connect(self, client, userdata, flags, rc):
        print("Succefully connected to broker")
        self.mqttClient.subscribe(self.broker_info['broker_topic'])
        self.mqttClient.on_message = self._on_broker_message

    def _on_broker_message(self, client, userdata, message):
        msg = str(message.payload.decode("utf-8"))
        print(msg)
        try:
            content = json.loads(msg)
        except:
            print("Could not parse message: {}".format(msg))
            return
        if 'action' in content.keys():
            if content["action"] == "start_recording":
                if 'target' in content.keys():
                    if 'videofile' and 'audiofile' in content['target'].keys():
                        v_path = content['target']['videofile']
                        a_path = content['target']['audiofile']
                        # Start recording
                        self.start_recording(v_path, a_path)
                        return
                    else:
                        print("Missing file targets : {}".format(content))
                else:
                    print("Missing file targets : {}".format(content))
            elif content['action'] == "stop_recording":
                self.stop_recording()
                self.publish_status()
                return
            elif content['action'] == "status":
                self.publish_status()
                
class AudioRecorder:
    chunk_size = 2048
    def __init__(self, sample_rate: int, channels: int):
        self.sample_rate = sample_rate
        self.channels = channels 

        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(format=pyaudio.paInt16,
                        channels=channels,
                        rate=sample_rate,
                        input=True,
                        frames_per_buffer=self.chunk_size)
        self.stream.stop_stream()
        self.recording = False

    def start_recording(self, file_path):
        #output file setup
        if os.path.isfile(file_path):
            os.remove(file_path)
        self.wavefile = wave.open(file_path, 'wb')
        self.wavefile.setnchannels(self.channels)
        self.wavefile.setsampwidth(2)
        self.wavefile.setframerate(self.sample_rate)
        self.recording = True
        self.th = Thread(target=self.record, args=())
        self.th.start()

    def record(self):
        self.stream.start_stream()
        print('Audio recording start')
        while self.recording:
            try:
                buffer = self.stream.read(self.chunk_size)
            except OSError as err:
                print("OSError occured: {}".format(err))

            self.wavefile.writeframes(buffer)
        
    def stop_recording(self):
        self.recording = False
        self.th.join()
        self.stream.stop_stream()
        self.wavefile.close()
        print('Audio recording stop')

class VideoRecorder:
    def __init__(self, camera_index: int):
        self.converter = DFE_Converter()
        self.init_vfeed(camera_index)
        self.recording = False
        
    def init_vfeed(self, camera_index: int):
        self.vfeed = cv2.VideoCapture(camera_index)
        self.fps = self.vfeed.get(cv2.CAP_PROP_FPS)
        self.input_size = int(self.vfeed.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.vfeed.get(cv2.CAP_PROP_FRAME_HEIGHT))        
        self.output_size = self.converter.shape()
        
    def status(self):
        return self.vfeed.isOpened()

    def __del__(self):
        if self.vfeed.isOpened():
            self.vfeed.release()    

    def start_recording(self, file_path):
        if os.path.isfile(file_path):
            os.remove(file_path)
        if self.vfeed.isOpened():
            self.vfeed.release()
        self.init_vfeed(DEFAULT_CAMERA_INDEX)
        if not self.vfeed.isOpened():
            self.th = None
            return

        print("Video recording start")
        self.th = Thread(target=self.record, args=(file_path,))
        self.th.start()
    
    def is_ready(self):
        return self.vfeed.isOpened()

    def record(self, file_path: str):
        self.output_video = cv2.VideoWriter(file_path, cv2.VideoWriter_fourcc(*'XVID'), self.fps, self.output_size)
        self.recording = True
        while(self.vfeed.isOpened() and self.recording):
            ret, frame = self.vfeed.read()
            if ret:
                frame = self.converter.convert(frame)
                self.output_video.write(frame)
            else:
                print("Capture returned false value, ending record")
                self.recording = False
        self.output_video.release()
        print("Video recording stop")

    def stop_recording(self):
        if self.recording:
            self.recording = False
            self.th.join()
            
        
class DFE_Converter:
    def __init__(self):
        with open(XMAP_FILE, 'rb') as f:
            assert f.readline() == b'P2\n' #format
            f.readline() #filename
            self.x_size, self.y_size = [int(v) for v in f.readline().split()] #map size
            f.readline().strip() #depth is not used but must be skipped
            self.xmap = np.ndarray((self.y_size, self.x_size))
            for i in range(self.y_size): 
                self.xmap[i] = [int(v) for v in f.readline().split()]
            self.xmap = self.xmap.astype(np.float32)

        with open(YMAP_FILE, 'rb') as f:
            assert f.readline() == b'P2\n'
            f.readline()
            x_size, y_size = [int(v) for v in f.readline().split()]
            assert (y_size, x_size) == (self.y_size, self.x_size)
            f.readline().strip()
            self.ymap = np.ndarray((y_size, x_size))
            for i in range(y_size): 
                self.ymap[i] = [int(v) for v in f.readline().split()]
            self.ymap = self.ymap.astype(np.float32)
    
    def convert(self, img):
        return cv2.remap(img, self.xmap, self.ymap, interpolation=cv2.INTER_LINEAR)

    def shape(self):
        return self.x_size, self.y_size

if __name__ == '__main__':
	main()


