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
import argparse
import paho.mqtt.client as mqtt
import tenacity

XMAP_FILE = "xmap_thetaS_1280x640.pgm"
YMAP_FILE = "ymap_thetaS_1280x640.pgm"
SUPPORTED_INPUT = (1280,720)
FPS = 15

def main():
    client = RecorderClient()
    client.run()

class RecorderClient:
    def __init__(self):
        with open('config.json', 'r') as f:
            self.broker_info = json.load(f)
        self.v_recorder = VideoRecorder(0,FPS)
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
            print("Recorder is off.")

    def start_recording(self, vfilepath, afilepath):
        self.recording = True
        self.v_recorder.start_recording(vfilepath)
    
    def stop_recording(self):
        self.v_recorder.stop_recording()
    
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
        try:
            if content['action'] == "start_recording":
                v_path = content['target']['videofile']
                a_path = content['target']['audiofile']
                # Start recording
                self.start_recording(v_path, a_path)
            elif content['action'] == "stop_recording":
                print("tadou")
                #stop recording
            elif content['action'] == "status":
                self.mqttClient.publish("recorder/status", "{'recording':'{}'}".format(self.recording))
        except:
            print("Message wrongly formated : {}".format(content))
                
class VideoRecorder:
    def __init__(self, camera_index: int, frame_rate: int):
        try:
            self.vfeed = cv2.VideoCapture(camera_index)
        except:
            raise IOError("Could not reach camera at index {}".format(camera_index))
        
        if frame_rate <= 0:
            raise AttributeError("Wrong frame_rate")
        self.fps = self.vfeed.get(cv2.CAP_PROP_FPS)
        self.input_size = int(self.vfeed.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.vfeed.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.framerate = frame_rate if frame_rate < self.fps else self.fps
        self.capture_delay = 1.0/frame_rate if frame_rate < self.fps else 0
        
        self.converter = DFE_Converter()
        self.output_size = self.converter.shape()
        self.recording = False

    def __del__(self):
        self.vfeed.release()

    def start_recording(self, file_path):
        self.th = Thread(target=self.record, args=(file_path))
        self.th.start()

    def record(self, file_path: str):
        self.output_video = cv2.VideoWriter(file_path, cv2.VideoWriter_fourcc(*'XVID'), self.framerate, self.output_size)
        start_t = time.time()
        self.recording = True
        while(self.vfeed.isOpened() and self.recording):
            _, frame = self.vfeed.read()
            if (time.time() - start_t) >= self.capture_delay or self.capture_delay == 0:
                start_t = time.time()
                frame = self.converter.convert(frame)
                self.output_video.write(frame)

    def stop_recording(self):
        self.recording = False
        self.th.join()
        self.output_video.release()


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


