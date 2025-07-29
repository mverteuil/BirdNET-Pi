from blinker import Namespace

signals = Namespace()

detection_signal = signals.signal("detection")
