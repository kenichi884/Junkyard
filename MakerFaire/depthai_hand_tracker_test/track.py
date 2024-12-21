#!/usr/bin/env python3

README = """
hogehoge

"""

print(README)

import zmq
context = zmq.Context.instance()
socket = context.socket(zmq.PUB)
socket.bind("ipc:///tmp/aaa")

from HandController import HandController
from toio import Point


# Smoothing filter
import numpy as np
class DoubleExpFilter:
    def __init__(self,smoothing=0.65,
                 correction=1.0,
                 prediction=0.85,
                 jitter_radius=250.,
                 max_deviation_radius=540.,
                 out_int=False):
        self.smoothing = smoothing
        self.correction = correction
        self.prediction = prediction
        self.jitter_radius = jitter_radius
        self.max_deviation_radius = max_deviation_radius
        self.count = 0
        self.filtered_pos = 0
        self.trend = 0
        self.raw_pos = 0
        self.out_int = out_int
        self.enable_scrollbars = False
    
    def reset(self):
        self.count = 0
        self.filtered_pos = 0
        self.trend = 0
        self.raw_pos = 0
    
    def update(self, pos):
        raw_pos = np.asanyarray(pos)
        if self.count > 0:
            prev_filtered_pos = self.filtered_pos
            prev_trend = self.trend
            prev_raw_pos = self.raw_pos
        if self.count == 0:
            self.shape = raw_pos.shape
            filtered_pos = raw_pos
            trend = np.zeros(self.shape)
            self.count = 1
        elif self.count == 1:
            filtered_pos = (raw_pos + prev_raw_pos)/2
            diff = filtered_pos - prev_filtered_pos
            trend = diff*self.correction + prev_trend*(1-self.correction)
            self.count = 2
        else:
            # First apply jitter filter
            diff = raw_pos - prev_filtered_pos
            length_diff = np.linalg.norm(diff)
            if length_diff <= self.jitter_radius:
                alpha = pow(length_diff/self.jitter_radius,1.5)
                # alpha = length_diff/self.jitter_radius
                filtered_pos = raw_pos*alpha \
                                + prev_filtered_pos*(1-alpha)
            else:
                filtered_pos = raw_pos
            # Now the double exponential smoothing filter
            filtered_pos = filtered_pos*(1-self.smoothing) \
                        + self.smoothing*(prev_filtered_pos+prev_trend)
            diff = filtered_pos - prev_filtered_pos
            trend = self.correction*diff + (1-self.correction)*prev_trend
        # Predict into the future to reduce the latency
        predicted_pos = filtered_pos + self.prediction*trend
        # Check that we are not too far away from raw data
        diff = predicted_pos - raw_pos
        length_diff = np.linalg.norm(diff)
        if length_diff > self.max_deviation_radius:
            predicted_pos = predicted_pos*self.max_deviation_radius/length_diff \
                        + raw_pos*(1-self.max_deviation_radius/length_diff)
        # Save the data for this frame
        self.raw_pos = raw_pos
        self.filtered_pos = filtered_pos
        self.trend = trend
        # Output the data
        if self.out_int:
            return predicted_pos.astype(int)
        else:
            return predicted_pos

smooth = DoubleExpFilter(smoothing=0.3, prediction=0.1, jitter_radius=700, out_int=True)

# Camera image size
cam_width = 1152
cam_height = 648


def move(event):
    # 中指付け根と手首の中点、角度を出す
    hand = event.hand
    if hand.lm_score < 0.95 :
        return 
    (dx, dy) =  hand.landmarks[0] - hand.landmarks[10]
    degree =  np.degrees(np.arctan2(dy, dx))
    (x, y) =  (hand.landmarks[0] + hand.landmarks[10])/ 2
    mx = x
    my =y 
    mx,my = smooth.update((mx,my))
    print(mx, my, degree)
    socket.send_string("hand/position", zmq.SNDMORE)
    socket.send_pyobj((x, y, degree))

def peace_gesture(event):
    socket.send_string("hand/gesture", zmq.SNDMORE)
    if event.trigger == "enter": 
        socket.send_pyobj("2enter")
        print("2enter")
    elif event.trigger == "leave":
        print("2leave")
        socket.send_pyobj("2leave")
def three_gesture(event):
    socket.send_string("hand/gesture", zmq.SNDMORE)
    if event.trigger == "enter": 
        socket.send_pyobj("3enter")
        print("3enter")
    elif event.trigger == "leave":
        print("3leave")
        socket.send_pyobj("3leave")

config = {

    'renderer' : {'enable': True},
    'pose_actions' : [

        {'name': 'MOVE', 'pose':['FIVE','FIST'], 'callback': 'move', "trigger":"continuous", "first_trigger_delay":0.1,},
        {'name': 'PEACE', 'pose':'PEACE', 'callback': 'peace_gesture', "trigger":"enter_leave", "first_trigger_delay":0.1},
        {'name': 'THREE', 'pose':'THREE', 'callback': 'three_gesture', "trigger":"enter_leave", "first_trigger_delay":0.1},

    ]
}

HandController(config).loop()