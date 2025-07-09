# ui/simulation_page.py
"""
Moduł definiujący stronę GUI odpowiedzialną za wyświetlanie i kontrolę
przebiegu symulacji.

Zawiera klasy:
- SimulationThread: Wątek do uruchamiania logiki symulacji w tle, aby nie blokować GUI.
- LegendWidget: Widget wyświetlający legendę elementów wizualizacji sieci.
- PlotResultsPage: Widget wyświetlający wykresy podsumowujące wyniki symulacji po jej zakończeniu.
- SimulationPage: Główny widget zarządzający interfejsem strony symulacji,
                  w tym widokiem sieci, przyciskami kontrolnymi, statusem
                  i przełączaniem między wizualizacją a wykresami.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsLineItem, QGraphicsRectItem, QTabWidget, QMessageBox,
    QProgressDialog, QFrame, QSizePolicy, QGridLayout, QScrollArea
)
from PySide6.QtGui import (
    QColor, QPen, QBrush, QPainter, QPixmap
)
from PySide6.QtCore import Qt, QThread, Signal, Slot

import matplotlib
import matplotlib.pyplot as plt
matplotlib.use('QtAgg')
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from simulation_core.simulation_manager import SimulationManager
from simulation_core.sensor import SensorState
from visualization.plot_generator import PlotGenerator
import tempfile
import os
import shutil

# Wątek do uruchamiania symulacji w tle
class SimulationThread(QThread):
    """
    Wątek poboczny do uruchamiania logiki symulacji bez blokowania głównego wątku GUI.

    Emituje sygnały informujące o postępie (statystyki rundy), zakończeniu
    symulacji (wszystkie zebrane statystyki) oraz błędach.
    """
    progress_signal = Signal(dict) # Sygnał emitujący statystyki rundy
    finished_signal = Signal(list) # Sygnał emitowany po zakończeniu symulacji (z wszystkimi statystykami)
    error_signal = Signal(str)     # Sygnał emitowany w przypadku błędu

    def __init__(self, config_file_path):
        """
        Konstruktor SimulationThread.

        Args:
            config_file_path (str): Ścieżka do pliku konfiguracyjnego dla SimulationManager.
            parent (QObject | None): Obiekt nadrzędny (domyślnie None).
        """
        super().__init__()
        self.config_file_path = config_file_path
        self.simulation_manager = None
        self._is_running = True

    def run(self):
        """
        Metoda uruchamiana po starcie wątku (simulation_thread.start()).

        Zawiera główną pętlę symulacji. Tworzy SimulationManager, uruchamia
        symulację runda po rundzie, emituje sygnały postępu i zbiera statystyki.
        Obsługuje zatrzymanie wątku na żądanie oraz błędy.
        """
        try:
            self.simulation_manager = SimulationManager(self.config_file_path)
            all_stats_accumulator = []
            for round_stats in self.simulation_manager.run_simulation():
                if not self._is_running:
                    print("SimulationThread: Stop requested.")
                    break
                self.progress_signal.emit(round_stats)
                all_stats_accumulator.append(round_stats)
            self.finished_signal.emit(all_stats_accumulator)
        except Exception as e:
            self.error_signal.emit(str(e))
            import traceback
            traceback.print_exc()
        finally:
            if self.config_file_path.startswith(tempfile.gettempdir()):
                try:
                    os.remove(self.config_file_path)
                    print(f"Removed temporary config file: {self.config_file_path}")
                except OSError as e:
                    print(f"Error removing temporary config file {self.config_file_path}: {e}")

    def stop(self):
        """
        Zatrzymuje działanie wątku symulacji.

        Ustawia wewnętrzną flagę `_is_running` na False. Jeśli obiekt
        SimulationManager posiada flagę `stop_simulation_flag`, ustawia
        ją również, aby umożliwić SimulationManagerowi czyste zakończenie
        bieżącej rundy.
        """
        self._is_running = False
        if self.simulation_manager and hasattr(self.simulation_manager, 'stop_simulation_flag'): 
            self.simulation_manager.stop_simulation_flag = True
        print("SimulationThread: stop() called.")

class LegendWidget(QFrame):
    """
    Widget wyświetlający legendę dla elementów wizualizacji sieci.

    Rysuje małe ikony/kształty z odpowiednimi kolorami i etykietami
    opisującymi, co oznaczają poszczególne elementy na wykresie sieci
    (np. stany sensorów, POI, połączenia, zasięgi).
    """
    def __init__(self, parent=None):
        """
        Konstruktor LegendWidget.

        Args:
            parent (QWidget | None): Obiekt nadrzędny (domyślnie None).
        """
        super().__init__(parent)
        self.setObjectName("LegendWidgetFrame")

        layout = QGridLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.setColumnStretch(1, 1) 

        legend_items_data = [
            ("#FFD700", "Węzeł Centralny - Stacja Bazowa", "ellipse"),
            ("#50C878", "Sensor Aktywny", "ellipse"),
            ("#A9A9A9", "Sensor Uśpiony", "ellipse"),
            ("#404040", "Sensor Martwy/Uszkodzony", "ellipse"),
            ("#32CD32", "POI Pokryty", "rect"),
            ("#FF4500", "POI Niepokryty", "rect"),
            ("#FF69B4", "Ścieżka do Stacji Bazowej", "line", Qt.PenStyle.SolidLine, 1.5),
            ("#1723FF", "Aktywny Link Komunikacyjny", "line", Qt.PenStyle.DashDotLine, 1.2),
            ("#FF8C00", "Zasięg Detekcji (Aktywny)", "line_dashed_custom", Qt.PenStyle.DashLine, 1),
            ("#ADD8E6", "Zasięg Komunikacji (Aktywny)", "line_dotted_custom", Qt.PenStyle.DotLine, 1)
        ]

        row = 0
        for color_hex, text, shape_type, *style_args in legend_items_data:
            color_label = QLabel()
            pixmap_size = 16
            pixmap = QPixmap(pixmap_size, pixmap_size)
            pixmap.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            pen_color = QColor(color_hex)
            brush_color = QColor(color_hex)
            
            pen = QPen(pen_color)
            line_width = 1.5
            if shape_type.startswith("line") and len(style_args) > 1:
                line_width = style_args[1]
            pen.setWidthF(line_width)

            if shape_type.startswith("line") and len(style_args) > 0:
                 pen.setStyle(style_args[0]) 
            
            brush = QBrush(brush_color)

            if shape_type == "ellipse":
                painter.setBrush(brush)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(2, 2, pixmap_size - 4, pixmap_size - 4)
            elif shape_type == "rect":
                painter.setBrush(brush)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(3, 3, pixmap_size - 6, pixmap_size - 6)
            elif shape_type.startswith("line"):
                painter.setPen(pen)
                painter.drawLine(1, pixmap_size // 2, pixmap_size - 2, pixmap_size // 2)
            
            painter.end()
            color_label.setPixmap(pixmap)
            color_label.setFixedSize(pixmap_size + 4, pixmap_size) 
            
            text_label = QLabel(text)

            layout.addWidget(color_label, row, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            layout.addWidget(text_label, row, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            row += 1
        
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)


class PlotResultsPage(QWidget):
    """
    Widget wyświetlający wykresy podsumowujące wyniki symulacji.

    Tworzy zakładki (QTabWidget), w każdej zakładce osadza wykres
    Matplotlib (FigureCanvasQTAgg) i wyświetla wygenerowane wykresy
    po zakończeniu symulacji.
    """
    def __init__(self, parent=None):
        """
        Konstruktor PlotResultsPage.

        Args:
            parent (QWidget | None): Obiekt nadrzędny (domyślnie None).
        """
        super().__init__(parent)
        layout = QVBoxLayout(self)
        
        self.plot_tabs = QTabWidget()
        layout.addWidget(self.plot_tabs)
        
        self.canvases = {} 

        self.plot_configs = {
            "sensor_counts": {"title": "Stany Sensorów", "method": "plot_sensor_counts"},
            "average_energy": {"title": "Średnia Energia", "method": "plot_average_energy"},
            "coverage_q": {"title": "Pokrycie POI (Q)", "method": "plot_coverage_q"},
            "pdr": {"title": "PDR", "method": "plot_pdr"},
            "latency": {"title": "Średnie Opóźnienie", "method": "plot_latency"},
        }

        for key, config in self.plot_configs.items():
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            canvas = FigureCanvas(Figure(figsize=(7, 5))) 
            tab_layout.addWidget(canvas)
            self.canvases[key] = canvas
            self.plot_tabs.addTab(tab, config["title"])

    def update_plots(self, all_stats_data):
        """
        Generuje i wyświetla wykresy wynikowe po zakończeniu symulacji.

        Wykorzystuje PlotGenerator do wygenerowania plików wykresów w tymczasowym
        katalogu, a następnie wczytuje te pliki jako obrazy i wyświetla je
        na odpowiednich zakładkach.

        Args:
            all_stats_data (list[dict]): Lista wszystkich zebranych statystyk
                                        z przebiegu symulacji.
        """
        if not all_stats_data:
            print("PlotResultsPage: No data to update plots.")
            return

        temp_plot_dir = tempfile.mkdtemp()
        plot_gen = PlotGenerator(all_stats_data, temp_plot_dir) 

        for key, config in self.plot_configs.items():
            canvas = self.canvases[key]
            canvas.figure.clear() 
            ax = canvas.figure.subplots() 

            try:
                plot_method = getattr(plot_gen, config["method"], None)
                if plot_method:
                    plot_method() 
                    
                    img_path = os.path.join(temp_plot_dir, f"{key}.png")

                    if os.path.exists(img_path):
                        img = plt.imread(img_path)
                        ax.imshow(img)
                        ax.axis('off') 
                    else:
                        print(f"PlotResultsPage: Image file not found for {key} at {img_path}")
                        ax.text(0.5, 0.5, f"Brak pliku wykresu dla\n{config['title']}", ha='center', va='center')
                else:
                     ax.text(0.5, 0.5, f"Metoda dla {key} nie znaleziona", ha='center', va='center')

            except Exception as e:
                print(f"Error generating plot {key}: {e}")
                ax.text(0.5, 0.5, f"Błąd generowania\n{config['title']}", ha='center', va='center', color='red')
            
            canvas.draw()
        
        try:
            shutil.rmtree(temp_plot_dir)
        except Exception as e:
            print(f"Error removing temp plot directory: {e}")

    def clear_plots(self):
        """
        Czyści wszystkie wykresy na zakładkach i wyświetla komunikat zastępczy.

        Wywoływana przed rozpoczęciem nowej symulacji.
        """
        for canvas in self.canvases.values():
            canvas.figure.clear()
            ax = canvas.figure.subplots()
            ax.text(0.5, 0.5, "Wykresy zostaną wygenerowane po symulacji.", ha='center', va='center')
            ax.axis('off')
            canvas.draw()


class SimulationPage(QWidget):
    """
    Główny widget strony symulacji w interfejsie GUI.

    Zawiera elementy interfejsu użytkownika do kontroli symulacji (start, stop),
    wyświetlania statusu i numeru rundy, a także QTabWidget do przełączania
    między wizualizacją sieci w czasie rzeczywistym (QGraphicsView) a
    wykresami wynikowymi (PlotResultsPage). Zarządza wątkiem symulacji
    i aktualizacją interfejsu na podstawie danych z wątku.
    """
    def __init__(self, go_back_callback, parent=None):
        """
        Konstruktor SimulationPage.

        Args:
            go_back_callback (callable): Funkcja zwrotna (callback) do wywołania
                                         po kliknięciu przycisku "Powrót do Konfiguracji".
            parent (QWidget | None): Obiekt nadrzędny (domyślnie None).
        """
        super().__init__(parent)
        self.go_back_callback = go_back_callback
        self.simulation_manager = None
        self.simulation_thread = None
        self.current_config_file = None
        self.all_simulation_stats = []
        self.progress_dialog = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15,15,15,15)

        control_panel_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Symulacji")
        self.start_btn.clicked.connect(self.start_simulation_processing)
        control_panel_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Zatrzymaj Symulację")
        self.stop_btn.clicked.connect(self.stop_simulation_processing)
        self.stop_btn.setEnabled(False)
        control_panel_layout.addWidget(self.stop_btn)

        control_panel_layout.addStretch()

        self.status_label = QLabel("Status: Oczekuje na konfigurację")
        self.status_label.setStyleSheet("font-style: italic; color: #A09CC9;")
        control_panel_layout.addWidget(self.status_label)
        main_layout.addLayout(control_panel_layout)

        self.display_tabs = QTabWidget()
        main_layout.addWidget(self.display_tabs, stretch=1)

        visualization_widget = QWidget()
        tab_content_layout = QHBoxLayout(visualization_widget)
        tab_content_layout.setContentsMargins(5,5,5,5)

        network_panel_widget = QWidget()
        network_panel_layout = QVBoxLayout(network_panel_widget)
        network_panel_layout.setContentsMargins(0,0,0,0)

        self.network_view = QGraphicsView()
        self.network_scene = QGraphicsScene()
        self.network_view.setScene(self.network_scene)
        self.network_view.setRenderHint(QPainter.Antialiasing)
        self.network_view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.network_view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.network_view.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.network_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        network_panel_layout.addWidget(self.network_view, 1)

        self.round_info_label = QLabel("Runda: 0")
        self.round_info_label.setAlignment(Qt.AlignCenter)
        network_panel_layout.addWidget(self.round_info_label)
        
        tab_content_layout.addWidget(network_panel_widget, 3)

        self.visualization_legend_widget = LegendWidget(self)
        
        legend_scroll_area = QScrollArea()
        legend_scroll_area.setWidgetResizable(True) 
        legend_scroll_area.setFrameShape(QFrame.Shape.StyledPanel)
        legend_scroll_area.setWidget(self.visualization_legend_widget)
        
        legend_scroll_area.setMinimumWidth(230) 
        legend_scroll_area.setMaximumWidth(280)

        tab_content_layout.addWidget(legend_scroll_area, 1)
        
        self.display_tabs.addTab(visualization_widget, "Wizualizacja Sieci")

        self.plot_results_page_widget = PlotResultsPage()
        self.display_tabs.addTab(self.plot_results_page_widget, "Wykresy Wynikowe")

        bottom_nav_layout = QHBoxLayout()
        bottom_nav_layout.addStretch()
        self.back_to_config_btn = QPushButton("Powrót do Konfiguracji")
        self.back_to_config_btn.clicked.connect(self.go_back_callback) 
        bottom_nav_layout.addWidget(self.back_to_config_btn)
        main_layout.addLayout(bottom_nav_layout)

        self.scene_items = {}

    def prepare_simulation(self, config_file_path: str) -> bool:
        """
        Przygotowuje stronę symulacji do uruchomienia nowej symulacji.

        Wczytuje ścieżkę do pliku konfiguracyjnego, resetuje stan strony
        (czyści scenę wizualizacji, statystyki, etykiety), ustawia granice
        sceny na podstawie wymiarów sieci z konfiguracji i włącza przycisk start.

        Args:
            config_file_path (str): Ścieżka do pliku konfiguracyjnego symulacji.

        Returns:
            bool: True, jeśli przygotowanie zakończyło się sukcesem; False, jeśli
                  plik konfiguracyjny nie istnieje lub wystąpił błąd.
        """
        self.current_config_file = config_file_path
        if not self.current_config_file or not os.path.exists(self.current_config_file):
            QMessageBox.critical(self, "Błąd", f"Plik konfiguracyjny nie istnieje: {self.current_config_file}")
            self.status_label.setText("Status: Błąd - brak pliku konfiguracyjnego.")
            return False
        
        self.status_label.setText(f"Status: Gotowy. Konfiguracja: {os.path.basename(config_file_path)}")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.all_simulation_stats = []
        self.network_scene.clear() 
        self.scene_items = {}
        self.round_info_label.setText("Runda: 0")
        self.plot_results_page_widget.clear_plots() 
        
        try:
            temp_manager = SimulationManager(config_file_path) 
            self.network_scene.setSceneRect(0, 0, temp_manager.config.getfloat('General', 'area_width', fallback=100),
                                                 temp_manager.config.getfloat('General', 'area_height', fallback=100))
            del temp_manager
        except Exception as e:
            QMessageBox.warning(self, "Ostrzeżenie", f"Nie można odczytać wymiarów sieci z konfiguracji: {e}")
            self.network_scene.setSceneRect(0,0,100,100) 
        self.network_view.fitInView(self.network_scene.sceneRect(), Qt.KeepAspectRatio)

        return True

    @Slot()
    def start_simulation_processing(self):
        """
        Slot wywoływany po kliknięciu przycisku "Start Symulacji".

        Uruchamia symulację w osobnym wątku (SimulationThread), aby nie blokować
        interfejsu GUI. Aktualizuje stan przycisków i etykiet oraz wyświetla
        okno dialogowe postępu.
        """
        if not self.current_config_file:
            QMessageBox.warning(self, "Start Symulacji", "Najpierw skonfiguruj parametry lub załaduj plik.")
            return

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.back_to_config_btn.setEnabled(False)
        self.status_label.setText("Status: Symulacja w toku...")
        self.all_simulation_stats = [] 
        self.plot_results_page_widget.clear_plots()

        self.progress_dialog = QProgressDialog("Uruchamianie symulacji...", "Anuluj", 0, 0, self) 
        self.progress_dialog.setWindowTitle("Postęp Symulacji")
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.setAutoReset(True)
        self.progress_dialog.show()

        self.simulation_thread = SimulationThread(self.current_config_file)
        self.simulation_thread.progress_signal.connect(self.update_simulation_state)
        self.simulation_thread.finished_signal.connect(self.simulation_finished)
        self.simulation_thread.error_signal.connect(self.simulation_error)
        self.simulation_thread.start()
    
    @Slot()
    def stop_simulation_processing(self):
        """
        Slot wywoływany po kliknięciu przycisku "Zatrzymaj Symulację"
        lub anulowaniu okna postępu.

        Zatrzymuje działanie wątku symulacji.
        """
        if self.simulation_thread and self.simulation_thread.isRunning():
            self.status_label.setText("Status: Zatrzymywanie symulacji...")
            self.simulation_thread.stop()
        self.stop_btn.setEnabled(False) 

    @Slot(dict)
    def update_simulation_state(self, round_stats: dict):
        """
        Slot wywoływany przez `progress_signal` z SimulationThread po każdej rundzie.

        Aktualizuje interfejs użytkownika o bieżące statystyki rundy,
        numer rundy oraz wizualizację stanu sieci na QGraphicsScene.
        Aktualizuje również okno dialogowe postępu.

        Args:
            round_stats (dict): Słownik zawierający statystyki z bieżącej rundy.
        """
        if not round_stats: return

        if self.progress_dialog and self.progress_dialog.isVisible():
            max_r = 100 # Domyślna wartość
            if self.simulation_thread and self.simulation_thread.simulation_manager and self.simulation_thread.simulation_manager.config:
                 max_r = self.simulation_thread.simulation_manager.config.getint("General", "max_rounds", fallback=100)
            current_r = round_stats.get('round', 0)
            
            if self.progress_dialog.maximum() == 0 and max_r > 0: # Ustaw maksimum, jeśli jeszcze nie ustawione
                self.progress_dialog.setMaximum(max_r)

            if current_r <= self.progress_dialog.maximum(): # Zapobiegaj błędom, jeśli current_r przekroczy max
                 self.progress_dialog.setValue(current_r)
            else: # Jeśli z jakiegoś powodu current_r > max_r, ustaw na max
                 self.progress_dialog.setValue(self.progress_dialog.maximum())

            self.progress_dialog.setLabelText(f"Przetwarzanie rundy {current_r}/{self.progress_dialog.maximum()}...")
            if self.progress_dialog.wasCanceled():
                self.stop_simulation_processing()
                return

        self.all_simulation_stats.append(round_stats)
        self.round_info_label.setText(f"Runda: {round_stats.get('round', 0)}")

        network_state = None
        if self.simulation_thread and self.simulation_thread.simulation_manager and self.simulation_thread.simulation_manager.network:
            network_state = self.simulation_thread.simulation_manager.network
        
        if not network_state: return

        items_to_remove_keys = []
        for item_key in list(self.scene_items.keys()):
            if item_key.startswith("range_sensing_") or \
               item_key.startswith("range_comm_") or \
               item_key.startswith("path_parent_") or \
               item_key.startswith("comm_link_"):
                items_to_remove_keys.append(item_key)
        
        for key_to_remove in items_to_remove_keys:
            items = self.scene_items.pop(key_to_remove, [])
            if not isinstance(items, list):
                items = [items]
            for graphics_item in items:
                if graphics_item and graphics_item.scene() == self.network_scene: 
                    self.network_scene.removeItem(graphics_item)
        
        for sensor_id, sensor in network_state.sensors.items():
            ellipse_key = f"sensor_ellipse_{sensor_id}"
            range_key = f"range_sensing_{sensor_id}" # Klucz dla zasięgu detekcji
            comm_range_key = f"range_comm_{sensor_id}" # Klucz dla zasięgu komunikacji

            color = QColor("blue") 
            edge_color = QColor("darkblue")
            if sensor.is_sink: color = QColor("#FFD700") 
            elif sensor.state == SensorState.DEAD or sensor.is_failed: color = QColor("#404040")
            elif sensor.state == SensorState.ACTIVE: color = QColor("#50C878") 
            elif sensor.state == SensorState.SLEEP: color = QColor("#A9A9A9") 
            
            sensor_size = 8
            if sensor.is_sink: sensor_size = 12

            if ellipse_key not in self.scene_items:
                ellipse = QGraphicsEllipseItem(sensor.pos[0] - sensor_size / 2, sensor.pos[1] - sensor_size / 2, sensor_size, sensor_size)
                self.network_scene.addItem(ellipse)
                self.scene_items[ellipse_key] = [ellipse] 
            else:
                ellipse = self.scene_items[ellipse_key][0]
                ellipse.setRect(sensor.pos[0] - sensor_size / 2, sensor.pos[1] - sensor_size / 2, sensor_size, sensor_size)
            
            ellipse.setBrush(QBrush(color))
            ellipse.setPen(QPen(edge_color, 1))
            ellipse.setZValue(2) 

            show_ranges = network_state.config.getboolean("Visualization", "show_ranges", fallback=False)
            if show_ranges and (sensor.state == SensorState.ACTIVE or sensor.is_sink) and not sensor.is_failed:
                if sensor.sensing_range > 0 and not sensor.is_sink:
                    sensing_r = QGraphicsEllipseItem(sensor.pos[0] - sensor.sensing_range, sensor.pos[1] - sensor.sensing_range,
                                                    sensor.sensing_range * 2, sensor.sensing_range * 2)
                    sensing_r.setPen(QPen(QColor("#FF8C00"), 1, Qt.DashLine)) 
                    sensing_r.setZValue(0)
                    self.network_scene.addItem(sensing_r)
                    self.scene_items[range_key] = [sensing_r]
                
                if sensor.comm_range > 0 :
                    comm_r = QGraphicsEllipseItem(sensor.pos[0] - sensor.comm_range, sensor.pos[1] - sensor.comm_range,
                                                  sensor.comm_range * 2, sensor.comm_range * 2)
                    comm_r.setPen(QPen(QColor("#ADD8E6"), 1, Qt.DotLine)) 
                    comm_r.setZValue(0)
                    self.network_scene.addItem(comm_r)
                    self.scene_items[comm_range_key] = [comm_r]

        for poi_idx, poi in enumerate(network_state.pois):
            poi_key = f"poi_{poi.id}"
            color = QColor("#32CD32") if poi.is_covered else QColor("#FF4500") 
            poi_size = 10
            if poi_key not in self.scene_items:
                rect = QGraphicsRectItem(poi.pos[0] - poi_size/2, poi.pos[1] - poi_size/2, poi_size, poi_size)
                self.network_scene.addItem(rect)
                self.scene_items[poi_key] = [rect]
            else:
                rect = self.scene_items[poi_key][0]
                rect.setRect(poi.pos[0] - poi_size/2, poi.pos[1] - poi_size/2, poi_size, poi_size)
            rect.setBrush(QBrush(color))
            rect.setZValue(1)


        show_paths = network_state.config.getboolean("Visualization", "show_paths", fallback=True)
        if show_paths:
            for sensor_id, sensor in network_state.sensors.items():
                if hasattr(sensor, 'parent_to_sink') and sensor.parent_to_sink is not None and \
                    sensor.state == SensorState.ACTIVE and not sensor.is_failed:
                    parent_sensor = network_state.get_sensor(sensor.parent_to_sink)
                    if parent_sensor and (not parent_sensor.is_failed or parent_sensor.is_sink):
                        path_key = f"path_parent_{sensor_id}"
                        line = QGraphicsLineItem(sensor.pos[0], sensor.pos[1], parent_sensor.pos[0], parent_sensor.pos[1])
                        line.setPen(QPen(QColor("#FF69B4"), 1.5, Qt.SolidLine)) 
                        line.setZValue(0) 
                        self.network_scene.addItem(line)
                        self.scene_items[path_key] = [line] 

                if sensor.state == SensorState.ACTIVE and not sensor.is_failed and sensor.data_buffer:
                    for packet_in_buffer in sensor.data_buffer:
                        if packet_in_buffer.next_hop_id is not None:
                            receiver = network_state.get_sensor(packet_in_buffer.next_hop_id)
                            if receiver and (receiver.state == SensorState.ACTIVE or receiver.is_sink) and not receiver.is_failed:
                                comm_link_key = f"comm_link_{sensor_id}_to_{receiver.id}_{packet_in_buffer.id}"
                                line = QGraphicsLineItem(sensor.pos[0], sensor.pos[1], receiver.pos[0], receiver.pos[1])
                                line.setPen(QPen(QColor("#1723FF"), 1, Qt.DashDotLine)) 
                                line.setZValue(0)
                                self.network_scene.addItem(line)
                                self.scene_items[comm_link_key] = [line]

        if self.display_tabs.currentIndex() == 0:
            self.network_view.viewport().update()


    @Slot(list)
    def simulation_finished(self, all_stats):
        """
        Slot wywoływany przez `finished_signal` z SimulationThread po zakończeniu symulacji.

        Zamyka okno dialogowe postępu, aktualizuje status, włącza przyciski
        kontrolne i generuje wykresy wynikowe.

        Args:
            all_stats (list[dict]): Lista wszystkich zebranych statystyk z przebiegu symulacji.
        """
        if self.progress_dialog: 
            self.progress_dialog.close()
            self.progress_dialog = None
            
        self.all_simulation_stats = all_stats 
        self.status_label.setText(f"Status: Symulacja zakończona po {len(all_stats)} rundach.")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.back_to_config_btn.setEnabled(True)
        
        if all_stats: # Generuj wykresy tylko jeśli są dane
            self.plot_results_page_widget.update_plots(self.all_simulation_stats)
            self.display_tabs.setCurrentIndex(1) 
            QMessageBox.information(self, "Koniec Symulacji", f"Symulacja zakończona. Zebrano {len(all_stats)} rund danych.")
        else: # Jeśli symulacja została zatrzymana przed zebraniem danych
            QMessageBox.information(self, "Koniec Symulacji", "Symulacja zakończona lub zatrzymana. Brak danych do wygenerowania wykresów.")


    @Slot(str)
    def simulation_error(self, error_message):
        if self.progress_dialog: 
            self.progress_dialog.close()
            self.progress_dialog = None

        self.status_label.setText(f"Status: Błąd symulacji!")
        QMessageBox.critical(self, "Błąd Symulacji", error_message)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.back_to_config_btn.setEnabled(True)

    def closeEvent(self, event): 
        self.stop_simulation_processing()
        # Upewnij się, że wątek zakończył działanie, jeśli aplikacja jest zamykana
        if self.simulation_thread and self.simulation_thread.isRunning():
            self.simulation_thread.wait(1000) # Poczekaj chwilę
        super().closeEvent(event)