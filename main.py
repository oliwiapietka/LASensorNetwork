# main.py
"""
Główny moduł startowy aplikacji GUI opartej na PySide6 (Qt).

Moduł ten inicjalizuje środowisko graficzne, ładuje niezbędne zasoby
(czcionki, style QSS), tworzy wymagane katalogi dla konfiguracji i wyników,
a następnie uruchamia główne okno aplikacji (MainWindow) i pętlę zdarzeń GUI.
Jest to punkt wejścia dla wersji aplikacji z interfejsem graficznym.
"""
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase, QFont

# Dodaj główny katalog projektu do ścieżki Pythona
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ui.main_window import MainWindow
from ui.styles import MAIN_STYLESHEET # Import stylów

if __name__ == '__main__':
    """"
    Sekcja główna uruchamiana, gdy skrypt jest wykonywany bezpośrednio.
    Inicjalizuje aplikację Qt i uruchamia GUI.
    """
    # 1. Inicjalizacja aplikacji Qt
    app = QApplication(sys.argv)

    # 2. Ładowanie niestandardowej czcionki (Inter)
    font_dir = os.path.join(project_root, 'assets', 'fonts')
    inter_font_path = os.path.join(font_dir, 'Inter_Regular2.ttf') # Możesz potrzebować innych wariantów (Bold, etc.)
    
    if os.path.exists(inter_font_path):
        # Dodaj czcionkę do bazy danych czcionek aplikacji
        font_id = QFontDatabase.addApplicationFont(inter_font_path)
        if font_id != -1:
            # Pobierz rodziny czcionek załadowanych z pliku
            font_families = QFontDatabase.applicationFontFamilies(font_id)
            if font_families:
                # Ustaw załadowaną czcionkę jako domyślną dla aplikacji
                app_font = QFont(font_families[0]) # Użyj pierwszej załadowanej rodziny
                app.setFont(app_font)
                #print(f"Successfully loaded and set font: {font_families[0]}")
            else:
                print(f"Warning: Font file {inter_font_path} loaded, but no font families found.")
        else:
            print(f"Warning: Could not load font from {inter_font_path}. Check Qt font logs for details.")
    else:
        print(f"Warning: Font file not found at {inter_font_path}. Using system default.")
    
    # 3. Zastosowanie globalnych stylów QSS
    # Style są definiowane w pliku ui/styles.py.
    app.setStyleSheet(MAIN_STYLESHEET)

    # 4. Utworzenie niezbędnych katalogów (jeśli nie istnieją)
    # Zapewnia istnienie katalogów do przechowywania konfiguracji, wyników i zasobów graficznych.
    os.makedirs(os.path.join(project_root, 'config'), exist_ok=True)
    os.makedirs(os.path.join(project_root, 'results'), exist_ok=True)
    os.makedirs(os.path.join(project_root, 'assets', 'icons'), exist_ok=True)

    # 5. Tworzenie i wyświetlanie głównego okna aplikacji
    # Instancja klasy MainWindow, która reprezentuje główne okno aplikacji GUI.
    window = MainWindow()
    window.show()

    # 6. Uruchomienie głównej pętli zdarzeń aplikacji
    # app.exec() blokuje wykonanie skryptu i czeka na zdarzenia (kliknięcia, wprowadzanie tekstu itp.).
    # Gdy główne okno zostanie zamknięte, pętla kończy działanie, a aplikacja się zamyka.
    sys.exit(app.exec())