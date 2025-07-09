# ui/main_window.py
"""
Moduł definiujący główne okno aplikacji GUI (MainWindow).

MainWindow jest kontenerem dla różnych "stron" aplikacji (widoków)
takich jak LandingPage, ConfigPage, ManualSettingsPage, i SimulationPage.
Wykorzystuje QStackedWidget do zarządzania przełączaniem między tymi stronami.
Obsługuje również podstawową logikę nawigacji i zamykania aplikacji.
"""
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QStackedWidget, QApplication
from PySide6.QtCore import Qt
import sys

from .landing_page import LandingPage
from .config_page import ConfigPage
from .manual_settings_page import ManualSettingsPage
from .simulation_page import SimulationPage
from .styles import MAIN_STYLESHEET
from PySide6.QtGui import QFontDatabase, QFont
import os

class MainWindow(QMainWindow):
    """
    Główna klasa okna aplikacji.

    Zarządza przełączaniem między różnymi widokami (stronami) aplikacji
    przy użyciu QStackedWidget. Inicjalizuje wszystkie strony i definiuje
    metody nawigacyjne.
    """
    def __init__(self):
        """
        Konstruktor klasy MainWindow.

        Inicjalizuje główne okno, ustawia tytuł i rozmiar, tworzy centralny
        widget z QVBoxLayout i QStackedWidget. Inicjalizuje wszystkie strony
        aplikacji i dodaje je do QStackedWidget. Ustawia początkową stronę.
        """
        super().__init__()

        # Ustawienia głównego okna
        self.setWindowTitle("Symulator Sieci Sensorowej WSN LA")
        self.setGeometry(100, 100, 1200, 800) # Domyślny rozmiar okna i pozycja okna

        # Centralny widget i layout - kontenery dla QStackedWidget
        self.central_widget = QWidget()
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0,0,0,0)

        self.stack = QStackedWidget()
        self.main_layout.addWidget(self.stack)

        # Inicjalizacja poszczególnych stron aplikacji
        # Przekazywanie funkcji nawigacyjnych do stron, aby mogły zmieniać widok
        self.landing_page = LandingPage(self.go_to_config_page, self.go_to_manual_settings)
        self.config_page = ConfigPage(self.go_to_landing_page, self.go_to_simulation_page)
        self.manual_settings_page = ManualSettingsPage(self.go_to_landing_page, self.go_to_simulation_page)
        self.simulation_page = SimulationPage(self.go_to_landing_page) # Na razie tylko powrót na landing

        # Dodawanie stron do QStackedWidget
        # Kolejność dodawania definiuje ich indeks w stosie
        self.stack.addWidget(self.landing_page)       # index 0
        self.stack.addWidget(self.config_page)        # index 1
        self.stack.addWidget(self.manual_settings_page) # index 2
        self.stack.addWidget(self.simulation_page)    # index 3

        self.setCentralWidget(self.central_widget)

        # Ustawienie początkowej strony
        self.go_to_landing_page()

    def go_to_landing_page(self):
        """Przełącza widok na stronę powitalną (LandingPage)."""
        self.stack.setCurrentIndex(0)

    def go_to_config_page(self, load_default=False):
        """"
        Przełącza widok na stronę konfiguracji z pliku (ConfigPage).

        Args:
            load_default (bool): Jeśli True, strona konfiguracji wczyta
                                 domyślne wartości konfiguracyjne z pliku.
        """
        if load_default:
            self.config_page.load_default_config_content()
        self.stack.setCurrentIndex(1)

    def go_to_manual_settings(self):
        """Przełącza widok na stronę ustawień ręcznych (ManualSettingsPage)."""
        self.stack.setCurrentIndex(2)

    def go_to_simulation_page(self, config_file_path: str):
        """
        Przełącza widok na stronę symulacji (SimulationPage).

        Przygotowuje stronę symulacji do uruchomienia na podstawie podanego
        pliku konfiguracyjnego przed przełączeniem widoku.

        Args:
            config_file_path (str): Ścieżka do pliku konfiguracyjnego, który
                                    zostanie przekazany do strony symulacji.
        """
        # Przekaż ścieżkę do pliku konfiguracyjnego do strony symulacji
        # Strona symulacji sama zainicjalizuje SimulationManager
        if self.simulation_page.prepare_simulation(config_file_path):
            self.stack.setCurrentIndex(3)
        else:
            print("Error preparing simulation from main_window")

    def closeEvent(self, event):
        """
        Obsługuje zdarzenie zamykania okna aplikacji.

        Zapewnia czyste zakończenie działających wątków symulacji
        oraz zwolnienie zasobów (np. zamknięcie okien wykresów), zanim
        aplikacja zostanie zamknięta.

        Args:
            event (QCloseEvent): Zdarzenie zamykania okna.
        """
        # Upewnij się, że wątek symulacji jest czysto zakończony, jeśli działa
        if hasattr(self.simulation_page, 'simulation_thread') and self.simulation_page.simulation_thread:
            if self.simulation_page.simulation_thread.isRunning():
                print("Attempting to stop simulation thread on close...")
                self.simulation_page.stop_simulation_processing()

        # Zamykanie wykresów Matplotlib, jeśli są zarządzane przez SimulationPage
        if hasattr(self.simulation_page, 'plot_results_page_widget'):
             if hasattr(self.simulation_page.plot_results_page_widget, 'clear_plots'):
                  self.simulation_page.plot_results_page_widget.clear_plots()

        event.accept()

# Sekcja do lokalnego testowania modułu main_window.py
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(MAIN_STYLESHEET)

    font_path = os.path.join(os.path.dirname(__file__), '../assets/fonts/Inter_Regular2.ttf')
    font_id = QFontDatabase.addApplicationFont(font_path)

    if font_id != -1:
        font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
        app_font = QFont(font_family)
        app.setFont(app_font)  # Ustaw czcionkę globalnie
    else:
        print("Nie udało się załadować czcionki.")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())