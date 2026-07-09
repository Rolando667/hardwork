"""Темна тема (QSS) для застосунку."""
from __future__ import annotations

DARK_QSS = """
* {
    font-size: 13px;
}
QWidget {
    background-color: #1e1f22;
    color: #e6e6e6;
    selection-background-color: #3b5bdb;
    selection-color: #ffffff;
}
QMainWindow, QDialog {
    background-color: #1e1f22;
}
QTabWidget::pane {
    border: 1px solid #33353a;
    top: -1px;
}
QTabBar::tab {
    background: #26282d;
    color: #c8c8c8;
    padding: 8px 16px;
    border: 1px solid #33353a;
    border-bottom: none;
}
QTabBar::tab:selected {
    background: #2f6feb;
    color: #ffffff;
}
QTabBar::tab:hover:!selected {
    background: #33363c;
}
QPushButton {
    background-color: #2f6feb;
    color: #ffffff;
    border: none;
    padding: 7px 14px;
    border-radius: 4px;
}
QPushButton:hover {
    background-color: #3b7bff;
}
QPushButton:pressed {
    background-color: #2559c0;
}
QPushButton:disabled {
    background-color: #3a3c42;
    color: #7a7a7a;
}
QPushButton#danger {
    background-color: #c0392b;
}
QPushButton#danger:hover {
    background-color: #e04b3a;
}
QPushButton#secondary {
    background-color: #3a3c42;
    color: #e6e6e6;
}
QPushButton#secondary:hover {
    background-color: #46484f;
}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #26282d;
    color: #e6e6e6;
    border: 1px solid #3a3c42;
    border-radius: 4px;
    padding: 5px;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #2f6feb;
}
QComboBox QAbstractItemView {
    background-color: #26282d;
    color: #e6e6e6;
    selection-background-color: #2f6feb;
}
QHeaderView::section {
    background-color: #2a2c31;
    color: #d0d0d0;
    padding: 6px;
    border: none;
    border-right: 1px solid #1e1f22;
    border-bottom: 1px solid #1e1f22;
}
QTableWidget, QTableView, QListWidget {
    background-color: #232428;
    alternate-background-color: #26282d;
    gridline-color: #33353a;
    border: 1px solid #33353a;
}
QTableWidget::item:selected, QListWidget::item:selected {
    background-color: #2f4a8a;
    color: #ffffff;
}
QCheckBox {
    spacing: 8px;
}
QProgressBar {
    background-color: #26282d;
    border: 1px solid #3a3c42;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
}
QProgressBar::chunk {
    background-color: #2f9e44;
    border-radius: 3px;
}
QScrollBar:vertical {
    background: #1e1f22;
    width: 12px;
}
QScrollBar::handle:vertical {
    background: #45474e;
    border-radius: 6px;
    min-height: 24px;
}
QScrollBar:horizontal {
    background: #1e1f22;
    height: 12px;
}
QScrollBar::handle:horizontal {
    background: #45474e;
    border-radius: 6px;
    min-width: 24px;
}
QLabel#warning {
    color: #ffa94d;
    font-weight: bold;
}
QLabel#hint {
    color: #9aa0a6;
}
QMenuBar {
    background-color: #26282d;
}
QMenuBar::item:selected {
    background: #2f6feb;
}
QMenu {
    background-color: #26282d;
    border: 1px solid #3a3c42;
}
QMenu::item:selected {
    background-color: #2f6feb;
}
"""
