import time
import os

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QHeaderView, QLabel, QMainWindow, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout,QWidget, QTabWidget, QListWidget, QListWidgetItem, QPushButton, QAbstractItemView
from PyQt5.QtCore import Qt
from queue import Queue

import json, ssl, sys, threading, websocket
from datetime import datetime

# Ayarlar dosyası
SETTINGS_FILE = "settings.json"


url = "wss://socket.haremaltin.com/socket.io/?EIO=4&transport=websocket"

headers = [
    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0",
    "Origin: https://izko.org.tr",
    "Accept-Language: tr-TR,tr;q=0.8,en-US;q=0.5,en;q=0.3",
    "Cache-Control: no-cache",
    "Pragma: no-cache",
    "Sec-GPC: 1"
]

# Global queue for communicating with UI thread
message_queue = Queue()
ws_instance = None

def on_open(ws):
    message_queue.put(("status", "Bağlandı"))

def on_message(ws, message):
    # Socket.IO connect paketi
    if message.startswith("0"):
        ws.send("40")
    
    # Mesaj "2" olduğunda socket'i kapat ve yeniden aç
    if message == "2":
        global ws_instance
        ws_instance.close()
    
    # 42["price_changed",...] formatındaki mesajları işle
    if message.startswith("42"):
        try:
            # Mesajı parse et: 42["price_changed",{...}]
            json_str = message[2:]  # "42" kısmını çıkar
            data = json.loads(json_str)
            
            if isinstance(data, list) and len(data) > 0:
                if data[0] == "price_changed" and len(data) > 1:
                    price_data = data[1]
                    
                    # UI queue'ya gönder
                    if isinstance(price_data, dict):
                        if "data" in price_data:
                            message_queue.put(("price_data", price_data["data"]))
                        else:
                            message_queue.put(("price_data", price_data))
        except Exception as e:
            pass

def on_error(ws, error):
    message_queue.put(("status", f"Hata: {error}"))

def on_close(ws, close_status_code, close_msg):
    message_queue.put(("status", "Bağlantı kapandı"))

def start_websocket():
    """WebSocket'i ayrı thread'de başlat"""
    global ws_instance
    
    while True:
        try:
            ws_instance = websocket.WebSocketApp(
                url,
                header=headers,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            ws_instance.run_forever(
                sslopt={
                    "cert_reqs": ssl.CERT_NONE
                }
            )
        except Exception as e:
            print(f"[ERROR] WebSocket hatası: {e}")
            time.sleep(2)
            print("[*] WebSocket yeniden bağlanılıyor...")

if __name__ == "__main__":
    class CompactWindow(QWidget):
        def __init__(self, close_callback=None):
            super().__init__()
            self.close_callback = close_callback
            self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            layout = QVBoxLayout()
            self.currency_label = QLabel("")
            self.currency_label.setFont(QFont("Arial", 10, QFont.Bold))
            self.sell_label = QLabel("")
            self.sell_label.setFont(QFont("Arial", 14))
            layout.addWidget(self.currency_label)
            layout.addWidget(self.sell_label)
            self.setLayout(layout)
            self.setStyleSheet("background-color: rgba(255,255,255,0.95); border: 1px solid #0078d4; padding:8px;")
            self._drag_pos = None

        def update_content(self, currency, sell):
            self.currency_label.setText(currency)
            self.sell_label.setText(str(sell))

        def mousePressEvent(self, event):
            if event.button() == Qt.RightButton:
                self.hide()
                if self.close_callback:
                    self.close_callback()
            elif event.button() == Qt.LeftButton:
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()

        def mouseMoveEvent(self, event):
            if self._drag_pos and event.buttons() & Qt.LeftButton:
                self.move(event.globalPos() - self._drag_pos)
                event.accept()

        def mouseReleaseEvent(self, event):
            self._drag_pos = None

    class PriceTrackerApp(QMainWindow):
        def __init__(self):
            super().__init__()
            self.init_ui()
            self.price_data = {}
            self.selected_assets = set()  # Seçili varlıklar
            self.current_compact_currency = None
            self.compact_window = None
            
            # Ayarları yükle
            self.load_settings()

            # Timer kurulumu
            self.timer = QTimer()
            self.timer.timeout.connect(self.check_queue)
            self.timer.start(100)
        
        def load_settings(self):
            """Kaydedilmiş ayarları yükle"""
            try:
                if os.path.exists(SETTINGS_FILE):
                    with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                        settings = json.load(f)
                        self.selected_assets = set(settings.get("selected_assets", []))
            except Exception as e:
                pass
        
        def save_settings(self):
            """Ayarları kaydet"""
            try:
                settings = {
                    "selected_assets": list(self.selected_assets)
                }
                with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, ensure_ascii=False, indent=2)
            except Exception as e:
                pass
        
        def closeEvent(self, event):
            """Pencere kapatılırken ayarları kaydet"""
            self.save_settings()
            event.accept()
        
        def update_time(self):
            """Saat etiketi güncelle (gün adı ile)"""
            days = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
            now = datetime.now()
            day_name = days[now.weekday()]
            current_time = now.strftime(f"{day_name} %d/%m/%Y %H:%M:%S")
            self.time_label.setText(current_time)

        def init_ui(self):
            self.setWindowTitle("Fiyat Takip Sistemi")
            self.setGeometry(100, 100, 1200, 700)

            # Modern stylesheet
            stylesheet = """
                QMainWindow {
                    background-color: #f0f0f0;
                }
                QTabWidget::pane {
                    border: 1px solid #cccccc;
                }
                QTabBar::tab {
                    background-color: #e0e0e0;
                    padding: 8px 20px;
                    margin-right: 2px;
                    border: 1px solid #cccccc;
                    border-bottom: none;
                }
                QTabBar::tab:selected {
                    background-color: #ffffff;
                    border-bottom: 2px solid #0078d4;
                }
                QTableWidget {
                    background-color: white;
                    gridline-color: #ddd;
                    border: 1px solid #ddd;
                }
                QTableWidget::item {
                    padding: 5px;
                }
                QHeaderView::section {
                    background-color: #0078d4;
                    color: white;
                    padding: 5px;
                    border: none;
                    font-weight: bold;
                }
                QLabel {
                    color: #333;
                }
                QPushButton {
                    background-color: #0078d4;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #106ebe;
                }
                QListWidget {
                    background-color: white;
                    border: 1px solid #ddd;
                }
            """
            self.setStyleSheet(stylesheet)

            # Central widget
            central_widget = QWidget()
            self.setCentralWidget(central_widget)

            main_layout = QVBoxLayout()

            # Status bar (solda durum, sağda saat)
            status_bar_layout = QHBoxLayout()
            
            self.status_label = QLabel("Bağlantı bekleniyor...")
            status_font = QFont()
            status_font.setPointSize(10)
            status_font.setBold(True)
            self.status_label.setFont(status_font)
            
            self.time_label = QLabel("")
            time_font = QFont("Arial", 12)
            time_font.setBold(True)
            self.time_label.setFont(time_font)
            self.time_label.setAlignment(Qt.AlignRight)
            self.time_label.setStyleSheet("color: red;")
            
            status_bar_layout.addWidget(self.status_label)
            status_bar_layout.addWidget(self.time_label)
            
            main_layout.addLayout(status_bar_layout)
            
            # Saat güncelleme timeri
            self.time_timer = QTimer()
            self.time_timer.timeout.connect(self.update_time)
            self.time_timer.start(1000)
            self.update_time()

            # Tab widget
            self.tabs = QTabWidget()

            # Tab 1: Fiyatlar
            self.create_prices_tab()
            self.tabs.addTab(self.prices_widget, "Fiyatlar")

            # Tab 2: Ayarlar
            self.create_settings_tab()
            self.tabs.addTab(self.settings_widget, "Ayarlar")

            main_layout.addWidget(self.tabs)
            central_widget.setLayout(main_layout)

        def create_prices_tab(self):
            """Fiyatlar sekmesi"""
            self.prices_widget = QWidget()
            layout = QVBoxLayout()

            # Table widget
            self.table = QTableWidget()
            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(["Varlık", "Fiyat", "Son Güncelleme"])

            # Tablo ayarları
            self.table.verticalHeader().setDefaultSectionSize(100)
            self.table.setWordWrap(True)
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)

            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(1, QHeaderView.Stretch)
            header.setSectionResizeMode(2, QHeaderView.Stretch)

            # Tablodaki satıra tıklamayı bağla
            self.table.cellClicked.connect(self.on_table_cell_clicked)

            layout.addWidget(self.table)
            self.prices_widget.setLayout(layout)

        def create_settings_tab(self):
            """Ayarlar sekmesi"""
            self.settings_widget = QWidget()
            layout = QVBoxLayout()

            # Başlık
            title = QLabel("Takip Edilecek Varlıkları Seçin")
            title_font = QFont()
            title_font.setPointSize(11)
            title_font.setBold(True)
            title.setFont(title_font)
            layout.addWidget(title)

            # Varlık listesi
            self.assets_list = QListWidget()
            self.assets_list.itemChanged.connect(self.on_asset_check_changed)
            layout.addWidget(self.assets_list)

            # Butonlar
            button_layout = QHBoxLayout()

            select_all_btn = QPushButton("Tümünü Seç")
            select_all_btn.clicked.connect(self.select_all_assets)
            button_layout.addWidget(select_all_btn)

            deselect_all_btn = QPushButton("Tümünü Kaldır")
            deselect_all_btn.clicked.connect(self.deselect_all_assets)
            button_layout.addWidget(deselect_all_btn)

            layout.addLayout(button_layout)
            self.settings_widget.setLayout(layout)

        def select_all_assets(self):
            """Tüm varlıkları seç"""
            self.assets_list.blockSignals(True)
            for i in range(self.assets_list.count()):
                item = self.assets_list.item(i)
                item.setCheckState(Qt.Checked)
                self.selected_assets.add(item.text())
            self.assets_list.blockSignals(False)
            self.save_settings()
            self.update_prices_display()
        
        def deselect_all_assets(self):
            """Tüm varlıkları seçimi kaldır"""
            self.assets_list.blockSignals(True)
            for i in range(self.assets_list.count()):
                item = self.assets_list.item(i)
                item.setCheckState(Qt.Unchecked)
            self.assets_list.blockSignals(False)
            self.selected_assets.clear()
            self.save_settings()
            self.update_prices_display()
        
        def on_asset_check_changed(self):
            """Varlık seçimi değiştiğinde"""
            self.selected_assets.clear()
            for i in range(self.assets_list.count()):
                item = self.assets_list.item(i)
                if item.checkState() == Qt.Checked:
                    self.selected_assets.add(item.text())
            self.save_settings()
            self.update_prices_display()
        
        def on_table_cell_clicked(self, row, column):
            """Tablo satırına tıklandığında compact modu aç"""
            item = self.table.item(row, 0)
            if not item:
                return
            currency = item.text()
            self.show_compact(currency)

        def show_compact(self, currency):
            """Compact moda geç ve seçili varlığı göster"""
            self.current_compact_currency = currency
            self.showMinimized()  # Normal modu minimize et (invisible)
            
            if not self.compact_window:
                self.compact_window = CompactWindow(close_callback=self.hide_compact)
            price_info = self.price_data.get(currency, {})
            sell = price_info.get('satis') or price_info.get('sell') or '-'
            self.compact_window.update_content(currency, sell)
            # Position top-right
            screen = QApplication.primaryScreen()
            geo = screen.availableGeometry()
            w, h = 220, 80
            x = geo.x() + geo.width() - w - 10
            y = geo.y() + 10
            self.compact_window.setGeometry(x, y, w, h)
            self.compact_window.show()
            self.compact_window.raise_()
            self.compact_window.activateWindow()

        def hide_compact(self):
            if self.compact_window:
                self.compact_window.hide()
            self.current_compact_currency = None
            self.showNormal()  # Normal modu geri aç

        def check_queue(self):
            """Queue'deki mesajları kontrol et ve UI güncelle"""
            while not message_queue.empty():
                msg_type, data = message_queue.get()

                if msg_type == "status":
                    self.status_label.setText(f"Durum: {data}")
                elif msg_type == "price_data":
                    self.update_prices(data)

        def update_prices(self, data):
            """Fiyat verilerini güncelle"""
            if not isinstance(data, dict):
                return

            self.price_data.update(data)

            # Ayarlar sekmesinde yeni varlıkları ekle
            for currency in self.price_data.keys():
                # Eğer liste boşsa veya varlık listede yoksa ekle
                found = False
                for i in range(self.assets_list.count()):
                    if self.assets_list.item(i).text() == currency:
                        found = True
                        break

                if not found:
                    item = QListWidgetItem(currency)
                    # Kaydedilmiş ayarlardan kontrol et
                    is_checked = currency in self.selected_assets
                    item.setCheckState(Qt.Checked if is_checked else Qt.Unchecked)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    self.assets_list.addItem(item)
                    if is_checked:
                        self.selected_assets.add(currency)

            self.update_prices_display()
            self.refresh_compact_price()

        def refresh_compact_price(self):
            if self.current_compact_currency and self.compact_window and self.compact_window.isVisible():
                info = self.price_data.get(self.current_compact_currency, {})
                sell = info.get('satis') or info.get('sell') or '-'
                self.compact_window.update_content(self.current_compact_currency, sell)

        def update_prices_display(self):
            """Tabloya seçili varlıkları göster"""
            # Tabloyu temizle
            self.table.setRowCount(0)

            # Seçili varlıkları göster (veya seçim yapılmadıysa hepsini göster)
            for currency, price_info in self.price_data.items():
                # Seçili varlık listesi boşsa tümünü göster, yoksa seçilenleri göster
                if self.selected_assets and currency not in self.selected_assets:
                    continue

                row = self.table.rowCount()
                self.table.insertRow(row)

                # Varlık adı
                asset_item = QTableWidgetItem(currency)
                asset_item.setFont(QFont("Arial", 9))
                self.table.setItem(row, 0, asset_item)

                # Fiyat bilgileri
                if isinstance(price_info, dict):
                    alis = price_info.get("alis", "-")
                    satis = price_info.get("satis", "-")
                    dusuk = price_info.get("dusuk", "-")
                    yuksek = price_info.get("yuksek", "-")
                    kapanis = price_info.get("kapanis", "-")
                    price_text = f"Alış: {alis}\nSatış: {satis}\nDüşük: {dusuk}\nYüksek: {yuksek}\nKapanış: {kapanis}"
                else:
                    price_text = str(price_info)

                price_item = QTableWidgetItem(price_text)
                price_item.setFont(QFont("Arial", 8))
                self.table.setItem(row, 1, price_item)

                # Son Güncelleme
                tarih = price_info.get("tarih", "-") if isinstance(price_info, dict) else "-"
                date_item = QTableWidgetItem(str(tarih))
                date_item.setFont(QFont("Arial", 9))
                self.table.setItem(row, 2, date_item)

            self.table.scrollToTop()

    # WebSocket thread'ini başlat
    ws_thread = threading.Thread(target=start_websocket, daemon=True)
    ws_thread.start()

    # PyQt5 uygulamasını başlat
    app = QApplication(sys.argv)
    window = PriceTrackerApp()
    window.show()
    sys.exit(app.exec_())

