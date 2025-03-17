# @Time    : ${11.19}
# @Author  : GYY


import sys

import serial
import serial.tools.list_ports
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTextEdit, QGroupBox, QGridLayout, QComboBox,
                               QDoubleSpinBox, QSpinBox)
from PySide6.QtCore import Qt

# 常量定义
BAUD_RATE = 115200
TIMEOUT = 0.5
VOLTAGE_RANGE = (-10.5, 10.5)
CURRENT_RANGE = (0, 40)
VOLTAGE_DECIMALS = 6
CURRENT_DECIMALS = 6
STEP_SIZE = 0.000001


class PowerSupplyControl(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.ser = None

    def init_ui(self):
        """初始化UI界面"""
        self.setWindowTitle("电源控制工具")
        self.setMinimumSize(700, 750)

        # 创建主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 创建串口对象
        self.ser = None

        # 创建组件
        self.response_group = self.create_response_group()
        connection_group = self.create_connection_group()
        control_group = self.create_control_group()
        limit_control_group = self.create_limit_control_group()
        command_group = self.create_command_group()
        system_control_group = self.create_system_control_group()
        control_group = self.create_control_group()
        limit_control_group = self.create_limit_control_group()
        calibration_group = self.create_calibration_group()
        command_group = self.create_command_group()

        # 添加到主布局
        main_layout.addWidget(connection_group)
        main_layout.addWidget(system_control_group)
        main_layout.addWidget(control_group)
        main_layout.addWidget(limit_control_group)
        main_layout.addWidget(calibration_group)
        main_layout.addWidget(command_group)
        main_layout.addWidget(self.response_group)

        # 刷新设备列表
        self.refresh_devices()

    def create_calibration_group(self):
        """创建校准控制组"""
        group = QGroupBox("校准控制")
        layout = QGridLayout()

        # 电压校准控制
        voltage_cal_label = QLabel("电压校准(V):")
        self.voltage_cal1_input = QDoubleSpinBox()
        self.voltage_cal1_input.setRange(-15, 15)
        self.voltage_cal1_input.setDecimals(6)
        self.voltage_cal1_input.setSingleStep(0.000001)
        self.voltage_cal1_input.setMinimumWidth(150)  # 设置最小宽度

        self.voltage_cal2_input = QDoubleSpinBox()
        self.voltage_cal2_input.setRange(-15, 15)
        self.voltage_cal2_input.setDecimals(6)
        self.voltage_cal2_input.setSingleStep(0.000001)
        self.voltage_cal2_input.setMinimumWidth(150)  # 设置最小宽度

        # 电流校准控制
        current_cal_label = QLabel("电流校准(mA):")
        self.current_cal1_input = QDoubleSpinBox()
        self.current_cal1_input.setRange(0, 40)
        self.current_cal1_input.setDecimals(6)
        self.current_cal1_input.setSingleStep(0.000001)
        self.current_cal1_input.setMinimumWidth(150)  # 设置最小宽度

        self.current_cal2_input = QDoubleSpinBox()
        self.current_cal2_input.setRange(0, 40)
        self.current_cal2_input.setDecimals(6)
        self.current_cal2_input.setSingleStep(0.000001)
        self.current_cal2_input.setMinimumWidth(150)  # 设置最小宽度

        # 校准按钮
        self.cal_voltage1_btn = QPushButton("校准电压参数1")
        self.cal_voltage1_btn.clicked.connect(self.calibrate_voltage1)
        self.cal_voltage2_btn = QPushButton("校准电压参数2")
        self.cal_voltage2_btn.clicked.connect(self.calibrate_voltage2)

        self.cal_current1_btn = QPushButton("校准电流参数3")
        self.cal_current1_btn.clicked.connect(self.calibrate_current1)
        self.cal_current2_btn = QPushButton("校准电流参数4")
        self.cal_current2_btn.clicked.connect(self.calibrate_current2)

        # 添加到布局
        layout.addWidget(voltage_cal_label, 0, 0)
        layout.addWidget(QLabel("参数1:"), 0, 1)
        layout.addWidget(self.voltage_cal1_input, 0, 2)
        layout.addWidget(self.cal_voltage1_btn, 0, 3)
        layout.addWidget(QLabel("参数2:"), 0, 4)
        layout.addWidget(self.voltage_cal2_input, 0, 5)
        layout.addWidget(self.cal_voltage2_btn, 0, 6)

        layout.addWidget(current_cal_label, 1, 0)
        layout.addWidget(QLabel("参数3:"), 1, 1)
        layout.addWidget(self.current_cal1_input, 1, 2)
        layout.addWidget(self.cal_current1_btn, 1, 3)
        layout.addWidget(QLabel("参数4:"), 1, 4)
        layout.addWidget(self.current_cal2_input, 1, 5)
        layout.addWidget(self.cal_current2_btn, 1, 6)

        # 设置列的拉伸因子
        layout.setColumnStretch(0, 1)  # 标签列
        layout.setColumnStretch(1, 0)  # "参数x"标签列
        layout.setColumnStretch(2, 3)  # 第一个输入框列
        layout.setColumnStretch(3, 1)  # 第一个按钮列
        layout.setColumnStretch(4, 0)  # "参数x"标签列
        layout.setColumnStretch(5, 3)  # 第二个输入框列
        layout.setColumnStretch(6, 1)  # 第二个按钮列

        # 设置列间距和边距
        layout.setHorizontalSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 添加校准开关按钮
        calibration_control_label = QLabel("校准控制:")
        calibration_control_label.setFixedWidth(80)

        # 创建水平布局来放置两个按钮
        cal_button_layout = QHBoxLayout()

        # 创建开启和关闭校准按钮
        self.cal_on_btn = QPushButton("开启校准")
        self.cal_off_btn = QPushButton("关闭校准")
        self.cal_on_btn.clicked.connect(self.turn_calibration_on)
        self.cal_off_btn.clicked.connect(self.turn_calibration_off)

        # 设置按钮大小
        button_width = 73  # (150 - spacing) / 2
        self.cal_on_btn.setFixedWidth(button_width)
        self.cal_off_btn.setFixedWidth(button_width)

        # 添加按钮到水平布局
        cal_button_layout.addWidget(self.cal_on_btn)
        cal_button_layout.addWidget(self.cal_off_btn)
        cal_button_layout.setSpacing(4)
        cal_button_layout.setContentsMargins(0, 0, 0, 0)

        # 在最后一行添加校准控制按钮
        layout.addWidget(calibration_control_label, 2, 0)
        layout.addLayout(cal_button_layout, 2, 2)

        group.setLayout(layout)
        return group

    def calibrate_voltage1(self):
        """电压校准参数1"""
        try:
            if self.ser:
                cal1 = self.voltage_cal1_input.value()
                # 设置正基准并测量
                self.send_scpi_command(f"*SAV 1,{cal1:.6f}")
                self.response_display.append(f"设置电压校准参数1: {cal1:.6f}V")
                self.response_display.append("电压参数1校准完成")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"电压校准参数1错误: {str(e)}")

    def calibrate_voltage2(self):
        """电压校准参数2"""
        try:
            if self.ser:
                cal2 = self.voltage_cal2_input.value()
                # 设置负基准并测量
                self.send_scpi_command(f"*SAV 2,{cal2:.6f}")
                self.response_display.append(f"设置电压校准参数2: {cal2:.6f}V")
                self.response_display.append("电压参数2校准完成")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"电压校准参数2错误: {str(e)}")

    def calibrate_current1(self):
        """电流校准参数3"""
        try:
            if self.ser:
                cal1 = self.current_cal1_input.value()
                # 设置40mA并测量
                self.send_scpi_command(f"*SAV 3,{cal1:.6f}")
                self.response_display.append(f"设置电流校准参数3: {cal1:.6f}mA")
                self.response_display.append("电流参数3校准完成")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"电流校准参数3错误: {str(e)}")

    def calibrate_current2(self):
        """电流校准参数4"""
        try:
            if self.ser:
                cal2 = self.current_cal2_input.value()
                # 设置1mA并测量
                self.send_scpi_command(f"*SAV 4,{cal2:.6f}")
                self.response_display.append(f"设置电流校准参数4: {cal2:.6f}mA")
                self.response_display.append("电流参数4校准完成")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"电流校准参数4错误: {str(e)}")

    def turn_calibration_on(self):
        """开启校准模式"""
        try:
            if self.ser:
                result = self.send_scpi_command("OUTPut:CALIbrate 1")
                if result is not None:
                    self.response_display.append("Calibrating...")
                    # 更新按钮状态
                    self.cal_on_btn.setEnabled(False)
                    self.cal_off_btn.setEnabled(True)
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"开启校准错误: {str(e)}")

    def turn_calibration_off(self):
        """关闭校准模式"""
        try:
            if self.ser:
                result = self.send_scpi_command("OUTPut:CALIbrate 0")
                if result is not None:
                    # 查询芯片名称
                    chip_name = self.send_scpi_command("*IDN?")
                    if chip_name:
                        self.response_display.append(f"芯片名称: {chip_name}")
                    # 更新按钮状态
                    self.cal_on_btn.setEnabled(True)
                    self.cal_off_btn.setEnabled(False)
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"关闭校准错误: {str(e)}")

    def create_connection_group(self):
        """创建连接控制组"""
        group = QGroupBox("连接设置")
        layout = QHBoxLayout()

        self.device_selector = QComboBox()
        self.refresh_btn = QPushButton("刷新设备列表")
        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self.handle_connection)

        layout.addWidget(QLabel("选择设备:"))
        layout.addWidget(self.device_selector)
        layout.addWidget(self.refresh_btn)
        layout.addWidget(self.connect_btn)

        group.setLayout(layout)
        return group

    def create_system_control_group(self):
        """创建系统控制组"""
        group = QGroupBox("系统控制")
        layout = QHBoxLayout()

        # 查询标识按钮
        self.idn_btn = QPushButton("查询标识(*IDN?)")
        self.idn_btn.clicked.connect(self.query_identification)

        # 重置按钮
        self.rst_btn = QPushButton("重置仪器(*RST)")
        self.rst_btn.clicked.connect(self.reset_instrument)

        # 查询固件版本按钮
        self.firmware_btn = QPushButton("查询固件版本")
        self.firmware_btn.clicked.connect(self.query_firmware)

        # 查询系统温度按钮
        self.temp_btn = QPushButton("查询系统温度")
        self.temp_btn.clicked.connect(self.query_temperature)

        # 添加到布局
        layout.addWidget(self.idn_btn)
        layout.addWidget(self.rst_btn)
        layout.addWidget(self.firmware_btn)
        layout.addWidget(self.temp_btn)

        group.setLayout(layout)
        return group

    def create_control_group(self):
        """创建电压电流控制组"""
        group = QGroupBox("电压电流控制")
        layout = QGridLayout()

        # 电压控制
        voltage_label = QLabel("电压设置(V):")
        voltage_label.setFixedWidth(80)  # 固定标签宽度
        self.voltage_spinbox = QDoubleSpinBox()
        self.voltage_spinbox.setRange(-15, 15)
        self.voltage_spinbox.setDecimals(6)
        self.voltage_spinbox.setSingleStep(0.000001)
        self.voltage_spinbox.setStepType(QDoubleSpinBox.StepType.AdaptiveDecimalStepType)
        self.voltage_spinbox.setMinimumWidth(150)  # 设置最小宽度
        self.voltage_spinbox.setFixedWidth(150)  # 固定输入框宽度

        # 电流控制
        current_label = QLabel("电流设置(mA):")
        current_label.setFixedWidth(80)  # 固定标签宽度
        self.current_spinbox = QDoubleSpinBox()
        self.current_spinbox.setRange(0, 40)
        self.current_spinbox.setDecimals(6)
        self.current_spinbox.setSingleStep(0.000001)
        self.current_spinbox.setStepType(QDoubleSpinBox.StepType.AdaptiveDecimalStepType)
        self.current_spinbox.setMinimumWidth(150)  # 设置最小宽度
        self.current_spinbox.setFixedWidth(150)  # 固定输入框宽度

        # 设置按钮
        self.set_voltage_btn = QPushButton("电压设置")
        self.set_voltage_btn.clicked.connect(self.set_voltage)
        self.set_voltage_btn.setFixedWidth(80)  # 固定按钮宽度

        self.set_current_btn = QPushButton("电流设置")
        self.set_current_btn.clicked.connect(self.set_current)
        self.set_current_btn.setFixedWidth(80)  # 固定按钮宽度

        # 输出控制
        output_label = QLabel("输出控制:")
        output_label.setFixedWidth(80)  # 固定标签宽度

        # 创建水平布局来放置两个按钮
        output_layout = QHBoxLayout()

        # 创建开启和关闭按钮
        self.output_on_btn = QPushButton("打开输出")
        self.output_off_btn = QPushButton("关闭输出")
        self.output_on_btn.clicked.connect(self.turn_output_on)
        self.output_off_btn.clicked.connect(self.turn_output_off)

        # 设置按钮大小
        button_width = 73  # (150 - spacing) / 2，使两个按钮总宽度等于150
        self.output_on_btn.setFixedWidth(button_width)
        self.output_off_btn.setFixedWidth(button_width)

        # 添加按钮到水平布局
        output_layout.addWidget(self.output_on_btn)
        output_layout.addWidget(self.output_off_btn)
        output_layout.setSpacing(4)  # 设置按钮之间的间距
        output_layout.setContentsMargins(0, 0, 0, 0)  # 移除边距

        # 创建网格布局
        grid = QGridLayout()
        grid.addWidget(voltage_label, 0, 0)
        grid.addWidget(self.voltage_spinbox, 0, 1)
        grid.addWidget(self.set_voltage_btn, 0, 2)

        grid.addWidget(current_label, 1, 0)
        grid.addWidget(self.current_spinbox, 1, 1)
        grid.addWidget(self.set_current_btn, 1, 2)

        grid.addWidget(output_label, 2, 0)
        grid.addLayout(output_layout, 2, 1)  # 使用addLayout

        # 添加水平弹性空间
        grid.setColumnStretch(3, 1)  # 最后一列添加弹性空间

        # 设置列间距
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        # 设置边距
        grid.setContentsMargins(10, 10, 10, 10)

        # 将网格布局设置为主布局
        layout.addLayout(grid, 0, 0)
        group.setLayout(layout)
        return group

    def create_command_group(self):
        """创建命令输入控制组"""
        group = QGroupBox("命令输入")
        layout = QHBoxLayout()

        self.command_input = QLineEdit()
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.send_command)

        layout.addWidget(self.command_input)
        layout.addWidget(self.send_btn)
        group.setLayout(layout)
        return group

    def create_response_group(self):
        group = QGroupBox("响应显示")
        layout = QVBoxLayout()

        self.response_display = QTextEdit()
        self.response_display.setReadOnly(True)

        layout.addWidget(self.response_display)
        group.setLayout(layout)
        return group

    def query_identification(self):
        """查询仪器标识"""
        try:
            if self.ser:
                response = self.send_scpi_command("*IDN?")
                self.response_display.append(f"仪器标识: {response}")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"查询标识错误: {str(e)}")

    def reset_instrument(self):
        """重置仪器"""
        try:
            if self.ser:
                self.send_scpi_command("*RST")
                self.response_display.append("仪器已重置")
                # 更新显示
                self.voltage_spinbox.setValue(0)
                self.current_spinbox.setValue(0)
                self.output_on_btn.setEnabled(True)
                self.output_off_btn.setEnabled(False)
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"重置错误: {str(e)}")

    def clear_status(self):
        """清除状态寄存器"""
        try:
            if self.ser:
                self.send_scpi_command("*CLS")
                self.response_display.append("状态寄存器已清除")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"清除状态错误: {str(e)}")

    def refresh_devices(self):
        """刷新可用的串口设备列表"""
        try:
            self.device_selector.clear()
            self.response_display.append("正在搜索设备...")

            # 获取所有串口设备
            ports = serial.tools.list_ports.comports()

            if ports:
                for port in ports:
                    self.device_selector.addItem(f"{port.device} - {port.description}")
                    self.response_display.append(f"发现设备: {port.device} - {port.description}")
            else:
                self.response_display.append("未找到串口设备")

        except Exception as e:
            self.response_display.append(f"刷新设备列表出错: {str(e)}")

    def handle_connection(self):
        """处理设备连接/断开"""
        try:
            if self.ser is None:
                # 获取选中的端口
                port = self.device_selector.currentText().split(' - ')[0]
                if not port:
                    self.response_display.append("请选择一个设备")
                    return

                # 连接设备
                self.ser = serial.Serial(
                    port=port,
                    baudrate=115200,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.5,  # 缩短超时时
                    write_timeout=0.5,  # 添加超
                    xonxoff=False,
                    rtscts=False,
                    dsrdtr=False
                )

                # 清空缓冲区
                self.ser.reset_input_buffer()
                self.ser.reset_output_buffer()

                self.connect_btn.setText("断开")
                self.response_display.append(f"已连接到设备: {port}")

                # 等待设备初始化
                import time
                time.sleep(0.2)

                # 发送初始化命令序列
                init_commands = [
                    "*CLS",  # 清除状态寄存器
                    "*RST",  # 重置设备
                    "SYST:REM",  # 切换到远程控制模式
                ]

                for cmd in init_commands:
                    self.send_scpi_command(cmd)
                    time.sleep(0.1)

                # 尝试获取设备标识
                response = self.send_scpi_command("*IDN?")
                if response:
                    self.response_display.append(f"设备标识: {response}")

                # 初始化输出按钮状态
                self.output_on_btn.setEnabled(True)
                self.output_off_btn.setEnabled(False)

                # 初始化校准按钮状态
                self.cal_on_btn.setEnabled(True)
                self.cal_off_btn.setEnabled(False)

            else:
                # 断开连接前发送本地控制命令
                try:
                    self.send_scpi_command("SYST:LOC")  # 切换到本地控制模式（如果设备持）
                except:
                    pass

                self.ser.close()
                self.ser = None
                self.connect_btn.setText("连接")
                self.response_display.append("已断开连接")

                # 重置输出按钮状态
                self.output_on_btn.setEnabled(True)
                self.output_off_btn.setEnabled(False)

                # 重置校准按钮状态
                self.cal_on_btn.setEnabled(True)
                self.cal_off_btn.setEnabled(False)
        except Exception as e:
            self.response_display.append(f"连接错误: {str(e)}")
            if self.ser:
                self.ser.close()
                self.ser = None

    def send_scpi_command(self, command):
        """发送SCPI命令并获取响应"""
        if not self.ser:
            self.log_message("错误：未连接到设备")
            return None

        try:
            if self.ser:
                # 清空输入缓冲区
                self.ser.reset_input_buffer()

                # 准备命令
                command = command.strip() + "\r\n"  # 使用 \r\n 作为终止符

                # 添加调试信息
                self.response_display.append(f"发送命令: {command.strip()}")

                # 发送命令
                self.ser.write(command.encode('ascii'))
                self.ser.flush()

                # 如果是查询命令或RCL命令，等待响应
                if "?" in command or command.strip().startswith("*RCL"):
                    # 给设备响应时间
                    import time
                    time.sleep(0.1)

                    # 读取响应
                    try:
                        # 首先尝试使用 ascii 解码
                        raw_response = self.ser.readline()
                        try:
                            response = raw_response.decode('ascii').strip()
                        except UnicodeDecodeError:
                            # 如果 ascii 解码失败，尝试使用 utf-8
                            try:
                                response = raw_response.decode('utf-8').strip()
                            except UnicodeDecodeError:
                                # 如果 utf-8 也失败，尝试使用 gb2312/gbk
                                try:
                                    response = raw_response.decode('gb2312').strip()
                                except UnicodeDecodeError:
                                    response = raw_response.decode('gbk', errors='ignore').strip()

                        if response:
                            self.response_display.append(f"收到响应: {response}")
                            # 检查是否是错误响应
                            if response.startswith("**ERROR"):
                                self.response_display.append("命令不被支持")
                                return None
                            return response
                        else:
                            self.response_display.append("警告：未收到响应")
                            return None
                    except Exception as e:
                        self.response_display.append(f"读取响应错误: {str(e)}")
                        # 如果所有解码方法都失败，返回十六进制格式的原始数据
                        hex_response = ' '.join([f'{b:02x}' for b in raw_response])
                        self.response_display.append(f"原始响应(hex): {hex_response}")
                        return None
                return "OK"  # 非查询命令返回OK
            else:
                self.response_display.append("错误：未连接到设备")
                return None
        except Exception as e:
            self.response_display.append(f"命令发送错误: {str(e)}")
            return None

    def send_command(self):
        """用户界面的命令发送"""
        try:
            command = self.command_input.text().strip()  # 去除首尾空格
            if not command:
                return

            # 检查是否是校准参数查询命令
            if command.startswith("*RCL"):
                try:
                    # 从命令中提取参数号
                    param_num = int(command.split("*RCL")[1].strip())
                    if 1 <= param_num <= 4:
                        # 发送命令并获取返回值
                        response = self.send_scpi_command(command)
                        if response:
                            try:
                                # 提取数值部分
                                import re
                                value_match = re.search(r'[-+]?\d*\.?\d+', response)
                                if value_match:
                                    param_value = float(value_match.group())
                                    # 根据参数编号显示对应的校准参数
                                    if param_num == 1:
                                        self.response_display.append(f"电压校准参数1 (最大值): {param_value:.6f}V")
                                        self.voltage_cal1_input.setValue(param_value)
                                    elif param_num == 2:
                                        self.response_display.append(f"电压校准参数2 (最小值): {param_value:.6f}V")
                                        self.voltage_cal2_input.setValue(param_value)
                                    elif param_num == 3:
                                        self.response_display.append(f"电流校准参数3 (40mA): {param_value:.6f}mA")
                                        self.current_cal1_input.setValue(param_value)
                                    elif param_num == 4:
                                        self.response_display.append(f"电流校准参数4 (1mA): {param_value:.6f}mA")
                                        self.current_cal2_input.setValue(param_value)
                                else:
                                    self.response_display.append(f"错误：无法从响应中提取数值 - {response}")
                            except ValueError as ve:
                                self.response_display.append(f"错误：数值转换失败 - {str(ve)}")
                        else:
                            self.response_display.append("错误：未收到有效响应")
                    else:
                        self.response_display.append("错误：参数范围应为1-4")
                except ValueError:
                    self.response_display.append("错误：参数必须是数字")
                except Exception as e:
                    self.response_display.append(f"错误：命令执行失败 - {str(e)}")
            else:
                # 处理其他命令
                response = self.send_scpi_command(command)
                if response:
                    self.response_display.append(f"响应: {response}")

            self.command_input.clear()
        except Exception as e:
            self.response_display.append(f"错误: {str(e)}")

    def set_voltage(self):
        """设置电压"""
        try:
            if self.ser:
                voltage = self.voltage_spinbox.value()

                # 使用SCPI命令设置电压
                self.send_scpi_command(f"SOURce:VOLTage:DC {voltage:.6f}")
                self.response_display.append(f"设置电压: {voltage:.6f}V")

                # 等待一小段时间让设备稳定
                import time
                time.sleep(0.1)

                # 查询实际电压值
                actual_voltage = self.query_voltage()
                if actual_voltage is not None:
                    self.response_display.append(f"实际电压: {actual_voltage:.6f}V")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"设置电压错误: {str(e)}")

    def set_current(self):
        """设置电流"""
        try:
            if self.ser:
                current = self.current_spinbox.value()

                # 用SCPI命令设置电流
                self.send_scpi_command(f"SOURce:CURRent:DC {current:.6f}")
                self.response_display.append(f"设置电流: {current:.6f}mA")

                # 等待一小段时间让设备稳定
                import time
                time.sleep(0.1)

                # 查询实际电流值
                actual_current = self.query_current()
                if actual_current is not None:
                    self.response_display.append(f"实际电流: {actual_current:.6f}mA")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"设置电流错误: {str(e)}")

    def turn_output_on(self):
        """打开输出"""
        try:
            if self.ser:
                result = self.send_scpi_command("OUTPut:STATe ON")
                if result is not None:
                    self.response_display.append("输出已打开")
                    # 更新按钮状态
                    self.output_on_btn.setEnabled(False)
                    self.output_off_btn.setEnabled(True)
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"输出控制错误: {str(e)}")

    def turn_output_off(self):
        """关闭输出"""
        try:
            if self.ser:
                result = self.send_scpi_command("OUTPut:STATe OFF")
                if result is not None:
                    self.response_display.append("输出已关闭")
                    # 更新按钮状态
                    self.output_on_btn.setEnabled(True)
                    self.output_off_btn.setEnabled(False)
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"输出控制错误: {str(e)}")

    def set_limits(self):
        """设置电压和电流的上下限"""
        try:
            if self.ser:
                # 设置电压上限
                volt_upper = self.voltage_upper_limit.value()
                self.send_scpi_command(f"SOURce:VOLTage:ULIMit {volt_upper:.6f}")

                # 设置电压下限
                volt_lower = self.voltage_lower_limit.value()
                self.send_scpi_command(f"SOURce:VOLTage:LLIMit {volt_lower:.6f}")

                # 设置电流上限
                curr_upper = self.current_upper_limit.value()
                self.send_scpi_command(f"SOURce:CURRent:ULIMit {curr_upper:.6f}")

                # 设置电流下限
                curr_lower = self.current_lower_limit.value()
                self.send_scpi_command(f"SOURce:CURRent:LLIMit {curr_lower:.6f}")

                self.response_display.append(
                    f"设置限制值:\n"
                    f"电压上限: {volt_upper:.6f}V\n"
                    f"电压下限: {volt_lower:.6f}V\n"
                    f"电流上限: {curr_upper:.6f}mA\n"
                    f"电流下限: {curr_lower:.6f}mA"
                )

                # # 查询设置结果
                # v_upper = self.send_scpi_command("SOURce:VOLTage:ULIMit?")
                # v_lower = self.send_scpi_command("SOURce:VOLTage:LLIMit?")
                # c_upper = self.send_scpi_command("SOURce:CURRent:ULIMit?")
                # c_lower = self.send_scpi_command("SOURce:CURRent:LLIMit?")
                #
                # if all([v_upper, v_lower, c_upper, c_lower]):
                #     self.response_display.append(
                #         f"实际限制值:\n"
                #         f"电压上限: {v_upper}V\n"
                #         f"电压下限: {v_lower}V\n"
                #         f"电流上限: {c_upper}mA\n"
                #         f"电流下限: {c_lower}mA"
                #     )
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"设置限值错误: {str(e)}")

    def query_firmware(self):
        """查询固件版本"""
        try:
            if self.ser:
                response = self.send_scpi_command("SYST:FIRM?")
                if response:
                    self.response_display.append(f"固件版本: {response}")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"查询固件版本错误: {str(e)}")

    def query_temperature(self):
        """查询系统温度"""
        try:
            if self.ser:
                response = self.send_scpi_command("SYST:TEMP?")
                if response:
                    try:
                        # 尝试提取数字部分
                        import re
                        temp_match = re.search(r'[-+]?\d*\.?\d+', response)
                        if temp_match:
                            temp = float(temp_match.group())
                            self.response_display.append(f"系统温度: {temp:.1f}°C")
                        else:
                            self.response_display.append(f"无法解析温度值: {response}")
                    except ValueError:
                        self.response_display.append(f"无效的温度数据: {response}")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"查询系统温度错误: {str(e)}")

    def create_limit_control_group(self):
        """创建限制控制组"""
        group = QGroupBox("限制控制")
        layout = QGridLayout()

        # 电压上下限控制
        voltage_limit_label = QLabel("电压限制(V):")
        voltage_limit_label.setFixedWidth(80)  # 固定标签宽度

        self.voltage_upper_limit = QDoubleSpinBox()
        self.voltage_upper_limit.setRange(-10.5, 10.5)
        self.voltage_upper_limit.setDecimals(6)
        self.voltage_upper_limit.setValue(10.5)
        self.voltage_upper_limit.setSingleStep(0.000001)
        self.voltage_upper_limit.setMinimumWidth(150)  # 设置最小宽度
        self.voltage_upper_limit.setFixedWidth(150)  # 固定输入框宽度

        self.voltage_lower_limit = QDoubleSpinBox()
        self.voltage_lower_limit.setRange(-10.5, 10.5)
        self.voltage_lower_limit.setDecimals(6)
        self.voltage_lower_limit.setValue(-10.5)
        self.voltage_lower_limit.setSingleStep(0.000001)
        self.voltage_lower_limit.setMinimumWidth(150)  # 设置最小宽度
        self.voltage_lower_limit.setFixedWidth(150)  # 固定输入框宽度

        # 电流上下限控制
        current_limit_label = QLabel("电流限制(mA):")
        current_limit_label.setFixedWidth(80)  # 固定标签宽度

        self.current_upper_limit = QDoubleSpinBox()
        self.current_upper_limit.setRange(0, 40)
        self.current_upper_limit.setDecimals(6)
        self.current_upper_limit.setValue(40)
        self.current_upper_limit.setSingleStep(0.000001)
        self.current_upper_limit.setMinimumWidth(150)  # 设置最小宽度
        self.current_upper_limit.setFixedWidth(150)  # 固定输入框宽度

        self.current_lower_limit = QDoubleSpinBox()
        self.current_lower_limit.setRange(0, 40)
        self.current_lower_limit.setDecimals(6)
        self.current_lower_limit.setValue(1)
        self.current_lower_limit.setSingleStep(0.000001)
        self.current_lower_limit.setMinimumWidth(150)  # 设置最小宽度
        self.current_lower_limit.setFixedWidth(150)  # 固定输入框宽度

        # 创建单独的按钮
        self.set_voltage_upper_btn = QPushButton("设置电压上限")
        self.set_voltage_upper_btn.clicked.connect(self.set_voltage_upper_limit)
        self.set_voltage_upper_btn.setFixedWidth(80)  # 固定按钮宽度

        self.set_voltage_lower_btn = QPushButton("设置电压下限")
        self.set_voltage_lower_btn.clicked.connect(self.set_voltage_lower_limit)
        self.set_voltage_lower_btn.setFixedWidth(80)  # 固定按钮宽度

        self.set_current_upper_btn = QPushButton("设置电流上限")
        self.set_current_upper_btn.clicked.connect(self.set_current_upper_limit)
        self.set_current_upper_btn.setFixedWidth(80)  # 固定按钮宽度

        self.set_current_lower_btn = QPushButton("设置电流下限")
        self.set_current_lower_btn.clicked.connect(self.set_current_lower_limit)
        self.set_current_lower_btn.setFixedWidth(80)  # 固定按钮宽度

        # 添加到布局
        # 第一行：电压上限
        layout.addWidget(voltage_limit_label, 0, 0)
        layout.addWidget(QLabel("上限:"), 0, 1)
        layout.addWidget(self.voltage_upper_limit, 0, 2)
        layout.addWidget(self.set_voltage_upper_btn, 0, 3)

        # 第二行：电压下限
        layout.addWidget(QLabel("下限:"), 1, 1)
        layout.addWidget(self.voltage_lower_limit, 1, 2)
        layout.addWidget(self.set_voltage_lower_btn, 1, 3)

        # 第三行：电流上限
        layout.addWidget(current_limit_label, 2, 0)
        layout.addWidget(QLabel("上限:"), 2, 1)
        layout.addWidget(self.current_upper_limit, 2, 2)
        layout.addWidget(self.set_current_upper_btn, 2, 3)

        # 第四行：电流下限
        layout.addWidget(QLabel("下限:"), 3, 1)
        layout.addWidget(self.current_lower_limit, 3, 2)
        layout.addWidget(self.set_current_lower_btn, 3, 3)

        # 设置列间距和边距
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 设置列的拉伸因子
        layout.setColumnStretch(0, 2)  # 第一列（标签）
        layout.setColumnStretch(1, 0)  # "上限/下限"标签最小
        layout.setColumnStretch(2, 3)  # 输入框列
        layout.setColumnStretch(3, 2)  # 按钮列
        layout.setColumnStretch(4, 1)  # 添加弹性空间

        # 设置对齐方式
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if isinstance(widget, QLabel) and ("上限:" in widget.text() or "下限:" in widget.text()):
                widget.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                widget.setContentsMargins(0, 0, 2, 0)

        group.setLayout(layout)
        return group

    def set_voltage_upper_limit(self):
        """设置电压上限"""
        try:
            if self.ser:
                volt_upper = self.voltage_upper_limit.value()
                self.send_scpi_command(f"SOUR:VOLT:ULIM {volt_upper:.6f}")
                self.response_display.append(f"设置电压上限: {volt_upper:.6f}V")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"设置电压上限错误: {str(e)}")

    def set_voltage_lower_limit(self):
        """设置电压下限"""
        try:
            if self.ser:
                volt_lower = self.voltage_lower_limit.value()
                self.send_scpi_command(f"SOURce:VOLTage:LLIMit {volt_lower:.6f}")
                self.response_display.append(f"设置电压下限: {volt_lower:.6f}V")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"设置电压下限错误: {str(e)}")

    def set_current_upper_limit(self):
        """设置电流上限"""
        try:
            if self.ser:
                curr_upper = self.current_upper_limit.value()
                self.send_scpi_command(f"SOURce:CURRent:ULIMit {curr_upper:.6f}")
                self.response_display.append(f"设置电流上限: {curr_upper:.6f}mA")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"设置电流上限错误: {str(e)}")

    def set_current_lower_limit(self):
        """设置电流下限"""
        try:
            if self.ser:
                curr_lower = self.current_lower_limit.value()
                self.send_scpi_command(f"SOURce:CURRent:LLIMit {curr_lower:.6f}")
                self.response_display.append(f"设置电流下限: {curr_lower:.6f}mA")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"设置电流下限错误: {str(e)}")

    def query_calibration_params(self):
        """查询所有校准参数"""
        try:
            if self.ser:
                # 查询所有校准参数
                params = []
                for i in range(1, 5):
                    response = self.send_scpi_command(f"*RCL {i}")
                    if response:
                        params.append(float(response))
                    else:
                        params.append(None)

                # 在UI上显示参数
                self.response_display.append("\n校准参数查询结果:")
                if params[0] is not None:
                    self.response_display.append(f"电压校准参数1: {params[0]:.6f}V")
                    self.voltage_cal1_input.setValue(params[0])
                if params[1] is not None:
                    self.response_display.append(f"电压校准参数2: {params[1]:.6f}V")
                    self.voltage_cal2_input.setValue(params[1])
                if params[2] is not None:
                    self.response_display.append(f"电流校准参数3: {params[2]:.6f}mA")
                    self.current_cal1_input.setValue(params[2])
                if params[3] is not None:
                    self.response_display.append(f"电流校准参数4: {params[3]:.6f}mA")
                    self.current_cal2_input.setValue(params[3])
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"查询校准参数错误: {str(e)}")

    def query_voltage(self):
        """查询实际电压值"""
        try:
            if self.ser:
                response = self.send_scpi_command("VOLT?")
                if response:
                    try:
                        # 提取数值部分
                        import re
                        value_match = re.search(r'[-+]?\d*\.?\d+', response)
                        if value_match:
                            voltage = float(value_match.group())
                            return voltage
                    except ValueError:
                        self.response_display.append("电压值解析错误")
                return None
            return None
        except Exception as e:
            self.response_display.append(f"电压查询错误: {str(e)}")
            return None

    def query_current(self):
        """查询实际电流值"""
        try:
            if self.ser:
                response = self.send_scpi_command("CURR?")
                if response:
                    try:
                        # 提取数值部分
                        import re
                        value_match = re.search(r'[-+]?\d*\.?\d+', response)
                        if value_match:
                            current = float(value_match.group())
                            return current
                    except ValueError:
                        self.response_display.append("电流值解析错误")
                return None
            return None
        except Exception as e:
            self.response_display.append(f"电流查询错误: {str(e)}")
            return None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PowerSupplyControl()
    window.show()
    sys.exit(app.exec())
