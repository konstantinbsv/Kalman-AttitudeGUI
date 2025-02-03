from pyqtgraph.opengl import GLViewWidget, GLMeshItem
import pyqtgraph as pg
from PyQt5 import QtWidgets, QtCore
import numpy as np
import serial
import struct
from collections import deque  # Faster list handling

class SerialDataPlotter(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Cube with Serial Data and Graphs")

        # Main layout setup
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QtWidgets.QHBoxLayout(self.central_widget)  # Horizontal split

        # Create a splitter to separate graphs and the right panel
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.layout.addWidget(self.splitter)

        # Left Side (Sensor Graphs)
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        self.splitter.addWidget(left_widget)

        # Create 6 subplots for ax, ay, az, gx, gy, gz
        self.plots = [pg.PlotWidget() for _ in range(6)]
        labels = ["ax", "ay", "az", "gx", "gy", "gz"]
        for plot, label in zip(self.plots, labels):
            plot.setLabel('left', label)
            plot.setLabel('bottom', 'Time')
            left_layout.addWidget(plot)  # Add plots to the left layout

        # Right Side (3D Cube + Roll/Pitch/Yaw + Radio Buttons)
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        self.splitter.addWidget(right_widget)

        # Create a nested splitter for the right panel (Vertical)
        right_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        right_layout.addWidget(right_splitter)

        # Top Half: Roll, Pitch, Yaw Graphs
        rpy_widget = QtWidgets.QWidget()
        rpy_layout = QtWidgets.QVBoxLayout(rpy_widget)
        right_splitter.addWidget(rpy_widget)

        self.rpy_plots = [pg.PlotWidget() for _ in range(3)]
        rpy_labels = ["Roll", "Pitch", "Yaw"]
        for plot, label in zip(self.rpy_plots, rpy_labels):
            plot.setLabel('left', label)
            plot.setLabel('bottom', 'Time')
            rpy_layout.addWidget(plot)

        # Middle: 3D Cube
        self.view = GLViewWidget()
        self.view.setCameraPosition(distance=10)
        right_splitter.addWidget(self.view)

        # Initialize cube mesh
        self.cube = self.create_3d_cube()
        self.view.addItem(self.cube)

        # Bottom: Radio Buttons for Algorithm Selection
        radio_widget = QtWidgets.QWidget()
        radio_layout = QtWidgets.QHBoxLayout(radio_widget)
        right_splitter.addWidget(radio_widget)

        self.algorithms = QtWidgets.QButtonGroup()
        self.alg1 = QtWidgets.QRadioButton("Method 1")
        self.alg2 = QtWidgets.QRadioButton("Method 2")
        self.alg3 = QtWidgets.QRadioButton("Method 3")

        self.alg1.setChecked(True)  # Default selection

        radio_layout.addWidget(self.alg1)
        radio_layout.addWidget(self.alg2)
        radio_layout.addWidget(self.alg3)

        self.algorithms.addButton(self.alg1, 1)
        self.algorithms.addButton(self.alg2, 2)
        self.algorithms.addButton(self.alg3, 3)

        # Connect radio buttons to method change function
        self.algorithms.buttonClicked.connect(self.change_algorithm)

        # Initialize serial port
        self.serial_port = serial.Serial('/dev/tty.usbserial-57460007651', 115200, timeout=1)

        self.PLOT_LENGTH = 50
        # Fast data storage using deque
        self.data = [deque(maxlen=self.PLOT_LENGTH) for _ in range(6)]  # ax, ay, az, gx, gy, gz
        self.angle_data = [deque(maxlen=self.PLOT_LENGTH) for _ in range(3)]  # Roll, Pitch, Yaw
        self.curves = [plot.plot() for plot in self.plots]
        self.angle_curves = [plot.plot() for plot in self.rpy_plots]

        # Set up timer for periodic updates
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(50)

        self.selected_algorithm = 1  # Default algorithm

    def create_3d_cube(self):
        """ Create a simple 3D cube """
        vertices = np.array([[-1, -1, -1],
                             [ 1, -1, -1],
                             [ 1,  1, -1],
                             [-1,  1, -1],
                             [-1, -1,  1],
                             [ 1, -1,  1],
                             [ 1,  1,  1],
                             [-1,  1,  1]])

        faces = np.array([[0, 1, 2], [0, 2, 3],
                          [4, 5, 6], [4, 6, 7],
                          [0, 1, 5], [0, 5, 4],
                          [2, 3, 7], [2, 7, 6],
                          [0, 3, 7], [0, 7, 4],
                          [1, 2, 6], [1, 6, 5]])

        cube_mesh = GLMeshItem(vertexes=vertices, faces=faces, color=(0.6, 0.6, 0.6, 1), shader='normalColor')
        return cube_mesh

    def change_algorithm(self, button):
        """ Change the calculation method for roll, pitch, yaw """
        self.selected_algorithm = self.algorithms.id(button)
        print(f"Selected algorithm: {self.selected_algorithm}")

    def get_serial_data(self):
        """ Reads line of serial data, checks for synchronization bytes, and returns the data """
        self.serial_port.reset_input_buffer()  # Clear input buffer
        line = self.serial_port.readline().strip()
        if line:
            if line[:2] == b'\xAA\x55':  # Check for sync header
                try:
                    values = struct.unpack('>6h', line[2:])  # Unpack the data (ax, ay, az, gx, gy, gz)
                    return values
                except:
                    pass
        return None  # Return None if no valid data found

    def update_plot(self):
        """ Update the 3D cube orientation and plots based on serial data """
        values = self.get_serial_data()
        if values:
            try:
                ax, ay, az, gx, gy, gz = values
                roll, pitch, yaw = self.calculate_rpy(ax, ay, az)
                    
                # Append new data (deques handle popping automatically)
                for i, val in enumerate(values):
                    self.data[i].append(val)

                for i, angle in enumerate([roll, pitch, yaw]):
                    self.angle_data[i].append(angle)

                # Only update graphs occasionally for performance
                if len(self.data[0]) % 5 == 0 or len(self.data[0]) <= self.PLOT_LENGTH:  
                    for i in range(6):
                        self.curves[i].setData(list(self.data[i]))

                    for i in range(3):
                        self.angle_curves[i].setData(list(self.angle_data[i]))

                # Update cube
                self.update_cube_orientation(roll, pitch)

            except Exception as e:
                print(f"Error in update_plot: {e}")

    def calculate_rpy(self, ax, ay, az):
        """ Compute roll, pitch, yaw based on selected algorithm """
        if self.selected_algorithm == 1:
            return np.arctan2(ay, az) * 180 / np.pi, np.arctan2(-ax, np.sqrt(ay**2 + az**2)) * 180 / np.pi, 0
        # Add other algorithm options here

    def update_cube_orientation(self, roll, pitch):
        self.cube.resetTransform()
        self.cube.rotate(roll, 1, 0, 0)
        self.cube.rotate(pitch, 0, 1, 0)

if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    window = SerialDataPlotter()
    window.show()
    app.exec_()
