#!/usr/bin/env python3
'''
 * Copyright (c) 2019 Linagora.
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

import cv2
import argparse
import os
import time
import numpy as np

XMAP_FILE = "xmap_thetaS_1280x640.pgm"
YMAP_FILE = "ymap_thetaS_1280x640.pgm"
SUPPORTED_INPUT = (1280,720)

def main():
    parser = argparse.ArgumentParser(description='Extract frames as jpg from video feed. To stop the recording press q')
    parser.add_argument('src', type=int, help="Camera index, 0 is the system default camera")
    parser.add_argument('target_video', help="Output video file *.avi")
    parser.add_argument('framerate', help='Frame per second. e.g.: 10 is 10 frames per second and 0.1 is one frame every 10 seconds', type=float)
    parser.add_argument('--profil', dest='profil', default='color', choices=['color', 'gray', 'grey'], help=' NOT IMPLEMENTED Color profil either gray or color (default is color)')
    parser.add_argument('--show', help="Display extracted images", action="store_true")
    parser.add_argument('--convert', help="Convert dualfisheye to equirectangular image", action="store_true")
    args = parser.parse_args()

    if args.framerate <= 0:
        print("Error: framerate argument must be > 0")
        parser.print_help()
        exit(-1)
    
    capture_delay = 1.0/args.framerate
    
    vfeed = cv2.VideoCapture(args.src)
    fps = vfeed.get(cv2.CAP_PROP_FPS)
    input_size = int(vfeed.get(cv2.CAP_PROP_FRAME_WIDTH)), int(vfeed.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print("Camera FPS : {}".format(fps))
    if args.convert:
        assert input_size == SUPPORTED_INPUT, "Only {} dualfisheye video input is supported for now".format(SUPPORTED_INPUT)
        converter = DFE_Converter()
    if args.framerate > fps:
        capture_delay = 0
    print("Capturing {} frame per second".format(args.framerate))
    start_t = time.time()
    output_size = converter.shape() if args.convert else input_size
    print("Output File: {} {}".format(args.target_video, output_size))
    output_video = cv2.VideoWriter(args.target_video, cv2.VideoWriter_fourcc(*'XVID'), args.framerate, output_size)
    count = 0
    while(vfeed.isOpened()):
        _, frame = vfeed.read()
        if (time.time() - start_t) >= capture_delay or capture_delay == 0 :
            count += 1
            start_t = time.time()
            if args.convert:
                frame = converter.convert(frame)
            output_video.write(frame)
            print("--> {} frames".format(count), end='\r')
            if args.show:
                cv2.imshow('Capture (press q to stop precording)', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    output_video.release()
    vfeed.release()
    cv2.destroyAllWindows()

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


