# Useful widgets
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

# Useful class for adding horizontal lines.
class QHLine(QtGui.QFrame):
    def __init__(self):
        super(QHLine, self).__init__()
        self.setFrameShape(QtGui.QFrame.HLine)
        self.setFrameShadow(QtGui.QFrame.Sunken)

