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
        command_group = self.create_command_group()
        system_control_group = self.create_system_control_group()
        control_group = self.create_control_group()
        calibration_group = self.create_calibration_group()
        command_group = self.create_command_group()

        # 添加到主布局
        main_layout.addWidget(connection_group)
        main_layout.addWidget(system_control_group)
        main_layout.addWidget(control_group)
        main_layout.addWidget(calibration_group)
        main_layout.addWidget(command_group)
        main_layout.addWidget(self.response_group)

        # 刷新设备列表
        self.refresh_devices()

    def create_calibration_group(self):
        """创建校准控制组"""
        group = QGroupBox("校准控制")
        layout = QGridLayout()

        # 添加校准参数选择下拉框
        param_label = QLabel("校准参数选择:")
        self.cal_param_selector = QComboBox()
        cal_params = [
            "档位1 (±10V)",
            "档位2 (±7.5V)",
            "档位3 (±5V)",
            "档位4 (±2.5V)",
            "档位5 (±2V)",
            "档位6 (±1.5V)",
            "档位7 (±1V)",
            "档位8 (±0.5V)"
        ]
        self.cal_param_selector.addItems(cal_params)
        self.cal_param_selector.setFixedWidth(150)
        self.cal_param_selector.currentIndexChanged.connect(self.update_cal_params)

        # 电压校准控制
        voltage_cal_label = QLabel("校准电压(V):")
        self.voltage_cal1_input = QDoubleSpinBox()
        self.voltage_cal1_input.setRange(-15, 15)
        self.voltage_cal1_input.setDecimals(6)
        self.voltage_cal1_input.setSingleStep(0.000001)
        self.voltage_cal1_input.setMinimumWidth(150)

        self.voltage_cal2_input = QDoubleSpinBox()
        self.voltage_cal2_input.setRange(-15, 15)
        self.voltage_cal2_input.setDecimals(6)
        self.voltage_cal2_input.setSingleStep(0.000001)
        self.voltage_cal2_input.setMinimumWidth(150)

        # 校准按钮
        self.cal_voltage_btn = QPushButton("设置校准值")
        self.cal_voltage_btn.clicked.connect(self.calibrate_voltage)

        # 校准控制按钮
        calibration_control_label = QLabel("校准控制:")
        cal_button_layout = QHBoxLayout()
        self.cal_on_btn = QPushButton("开启校准")
        self.cal_off_btn = QPushButton("关闭校准")
        self.cal_on_btn.clicked.connect(self.turn_calibration_on)
        self.cal_off_btn.clicked.connect(self.turn_calibration_off)

        button_width = 73
        self.cal_on_btn.setFixedWidth(button_width)
        self.cal_off_btn.setFixedWidth(button_width)

        cal_button_layout.addWidget(self.cal_on_btn)
        cal_button_layout.addWidget(self.cal_off_btn)
        cal_button_layout.setSpacing(4)
        cal_button_layout.setContentsMargins(0, 0, 0, 0)

        # 添加到布局
        layout.addWidget(param_label, 0, 0)
        layout.addWidget(self.cal_param_selector, 0, 1, 1, 2)

        layout.addWidget(voltage_cal_label, 1, 0)
        layout.addWidget(self.voltage_cal1_input, 1, 1)
        layout.addWidget(self.voltage_cal2_input, 1, 2)
        layout.addWidget(self.cal_voltage_btn, 1, 3)

        layout.addWidget(calibration_control_label, 2, 0)
        layout.addLayout(cal_button_layout, 2, 1, 1, 2)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 2)
        layout.setColumnStretch(2, 2)
        layout.setColumnStretch(3, 1)

        layout.setHorizontalSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        group.setLayout(layout)
        return group

    def update_cal_params(self):
        """更新校准参数显示"""
        try:
            if self.ser:
                # 获取当前选择的档位索引 (0-7)
                range_index = self.cal_param_selector.currentIndex()
                # 计算对应的参数索引 (1-16)
                param_index1 = range_index * 2 + 1  # 正电压参数
                param_index2 = range_index * 2 + 2  # 负电压参数

                # 查询对应的校准参数
                response1 = self.send_scpi_command(f"*RCL {param_index1}")
                response2 = self.send_scpi_command(f"*RCL {param_index2}")

                if response1 and response2:
                    try:
                        value1 = float(response1)
                        value2 = float(response2)
                        self.voltage_cal1_input.setValue(value1)
                        self.voltage_cal2_input.setValue(value2)

                        range_text = self.cal_param_selector.currentText()
                        self.response_display.append(
                            f"已加载{range_text}校准参数:\n"
                            f"正电压参数{param_index1}: {value1:.6f}V\n"
                            f"负电压参数{param_index2}: {value2:.6f}V"
                        )
                    except ValueError:
                        self.response_display.append("校准参数格式错误")
                else:
                    self.response_display.append("未能获取校准参数")
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"更新校准参数错误: {str(e)}")

    def calibrate_voltage(self):
        """设置校准参数"""
        try:
            if self.ser:
                # 获取当前选择的档位索引 (0-7)
                range_index = self.cal_param_selector.currentIndex()
                # 计算对应的参数索引 (1-16)
                param_index1 = range_index * 2 + 1  # 正电压参数
                param_index2 = range_index * 2 + 2  # 负电压参数

                # 获取校准值
                cal_value1 = self.voltage_cal1_input.value()
                cal_value2 = self.voltage_cal2_input.value()

                # 设置校准参数
                self.send_scpi_command(f"*SAV {param_index1},{cal_value1:.6f}")
                self.send_scpi_command(f"*SAV {param_index2},{cal_value2:.6f}")

                range_text = self.cal_param_selector.currentText()
                self.response_display.append(
                    f"设置{range_text}校准参数:\n"
                    f"正电压参数{param_index1}: {cal_value1:.6f}V\n"
                    f"负电压参数{param_index2}: {cal_value2:.6f}V"
                )
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"校准错误: {str(e)}")

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

        # 添加电压量程选择下拉框
        self.voltage_range_selector = QComboBox()
        self.voltage_range_selector.addItems(['10V', '7.5V', '5V', '2.5V', '2V', '1.5V', '1V', '0.5V'])
        self.voltage_range_selector.setFixedWidth(80)  # 固定下拉框宽度
        self.voltage_range_selector.currentIndexChanged.connect(self.set_voltage_range)

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

        # 修改网格布局
        grid = QGridLayout()
        grid.addWidget(voltage_label, 0, 0)
        grid.addWidget(self.voltage_spinbox, 0, 1)
        grid.addWidget(self.voltage_range_selector, 0, 2)  # 添加量程选择器
        grid.addWidget(self.set_voltage_btn, 0, 3)

        grid.addWidget(current_label, 1, 0)
        grid.addWidget(self.current_spinbox, 1, 1)
        grid.addWidget(self.set_current_btn, 1, 3)

        grid.addWidget(output_label, 2, 0)
        grid.addLayout(output_layout, 2, 1)  # 使用addLayout

        # 添加水平弹性空间
        grid.setColumnStretch(4, 1)  # 最后一列添加弹性空间

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
                    timeout=0.5,  # 缩短超时
                    write_timeout=0.5,  # 添加超时
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

    def set_voltage_range(self):
        """设置电压量程"""
        try:
            if self.ser:
                # 获取选中的量程值
                range_text = self.voltage_range_selector.currentText()
                range_value = float(range_text.replace('V', ''))

                # 发送SCPI命令设置量程
                self.send_scpi_command(f"VOLT:RANG {range_value}")
                self.response_display.append(f"设置电压量程: {range_value}V")

                # 根据量程更新电压输入框的范围
                self.voltage_spinbox.setRange(-range_value, range_value)
            else:
                self.response_display.append("错误：未连接到仪器")
        except Exception as e:
            self.response_display.append(f"设置电压量程错误: {str(e)}")

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
