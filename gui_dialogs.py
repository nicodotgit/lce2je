import typing
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QRadioButton, QButtonGroup, 
    QTableWidget, QTableWidgetItem, QHeaderView, 
    QComboBox, QLineEdit, QMessageBox, QCheckBox, QWidget
)
from PyQt6.QtCore import Qt

class lce2jePlayerMappingDialog(QDialog):
    def __init__(self, players, parent=None):
        super().__init__(parent)
        self.setWindowTitle("lce2je Player Mapping")
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        self.resize(400, 300)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select which players to keep, and choose the Host:"))
        
        self.table = QTableWidget(len(players), 3)
        self.table.setHorizontalHeaderLabels(["Player", "Keep?", "Is Host?"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        
        self.keep_checkboxes = {}
        self.host_radios = {}
        
        self.bg = QButtonGroup(self)
        
        # Add a "No Host" radio
        self.no_host_radio = QRadioButton("None")
        self.bg.addButton(self.no_host_radio)
        
        for row, p in enumerate(players):
            item = QTableWidgetItem(p)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item)
            
            cb_keep = QCheckBox()
            cb_keep.setChecked(True)
            self.keep_checkboxes[p] = cb_keep
            
            # center checkbox
            cb_widget = QHBoxLayout()
            cb_widget.setContentsMargins(0, 0, 0, 0)
            cb_widget.addWidget(cb_keep)
            cb_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_container = QWidget()
            cb_container.setLayout(cb_widget)
            self.table.setCellWidget(row, 1, cb_container)
            
            rb_host = QRadioButton()
            self.bg.addButton(rb_host)
            if row == 0:
                rb_host.setChecked(True)
            self.host_radios[p] = rb_host
            
            rb_widget = QHBoxLayout()
            rb_widget.setContentsMargins(0, 0, 0, 0)
            rb_widget.addWidget(rb_host)
            rb_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rb_container = QWidget()
            rb_container.setLayout(rb_widget)
            self.table.setCellWidget(row, 2, rb_container)
            
        layout.addWidget(self.table)
        
        no_host_layout = QHBoxLayout()
        no_host_layout.addStretch()
        no_host_layout.addWidget(QLabel("No Host (Skip Injection):"))
        no_host_layout.addWidget(self.no_host_radio)
        layout.addLayout(no_host_layout)
        
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)
        
    def get_selections(self):
        kept_players = []
        host_player = ""
        
        for p, cb in self.keep_checkboxes.items():
            if cb.isChecked():
                kept_players.append(p)
                
        for p, rb in self.host_radios.items():
            if rb.isChecked() and p in kept_players:
                host_player = p
                
        return kept_players, host_player

class CancelDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cancel Conversion")
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        self.resize(350, 150)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Conversion Paused.</b><br>Do you want to Save progress, Nuke (delete) progress, or Resume?"))
        
        self.bg = QButtonGroup(self)
        
        self.rb_s = QRadioButton("Save progress and exit")
        self.rb_n = QRadioButton("Nuke (safely delete) progress and exit")
        self.rb_c = QRadioButton("Cancel and resume conversion")
        
        self.bg.addButton(self.rb_s)
        self.bg.addButton(self.rb_n)
        self.bg.addButton(self.rb_c)
        
        self.rb_c.setChecked(True)
        
        layout.addWidget(self.rb_s)
        layout.addWidget(self.rb_n)
        layout.addWidget(self.rb_c)
        
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)
        
    def get_action(self):
        if self.rb_s.isChecked(): return "s"
        if self.rb_n.isChecked(): return "n"
        return "c"

