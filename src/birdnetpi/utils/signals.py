from blinker import Namespace

birdnet_signals = Namespace()

detection_event = birdnet_signals.signal("detection-event")
