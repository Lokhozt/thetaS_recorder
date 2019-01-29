# Recorder

Simple script that allow to record a stream from a camera using openCV. It also allows to convert DualFisheye images to equirectangular on the spot.
It has been designed to process a stream from a Ricoh ThetaS camera but can be adjusted for any camera.

### Before starting

The script recquires Numpy, opencv and argparse.

### Usage
```
usage: recorder.py [-h] [--profil {color,gray,grey}] [--show] [--convert]
                   src target_video framerate

Save video from camera. To stop the recording press q

positional arguments:
  src                   Camera index, 0 is the system default camera
  target_video          Output video file *.avi
  framerate             Frame per second. e.g.: 10 is 10 frames per second and
                        0.1 is one frame every 10 seconds

optional arguments:
  -h, --help            show this help message and exit
  --profil {color,gray,grey}
                        NOT IMPLEMENTED Color profil either gray or color
                        (default is color)
  --show                Display extracted images
  --convert             Convert dualfisheye to equirectangular image

```

###Licence
See LICENCE.txt

