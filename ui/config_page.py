# ui/config_page.py
"""
Moduł definiujący stronę GUI umożliwiającą wczytywanie, edycję i zapisywanie
plików konfiguracyjnych symulacji.

Użytkownik może przeglądać system plików w poszukiwaniu istniejących plików
konfiguracyjnych, wczytywać ich zawartość do edytora tekstowego, modyfikować
ją, zapisywać zmiany do bieżącego pliku lub zapisywać jako nowy plik.
Strona umożliwia również załadowanie domyślnej konfiguracji oraz uruchomienie
symulacji z aktualnie załadowanego/edytowanego pliku.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QFileDialog, QMessageBox, QLabel
from PySide6.QtCore import Qt, Slot
import os

class ConfigPage(QWidget):
    """
    Widget reprezentujący stronę edytora pliku konfiguracyjnego.

    Umożliwia interakcję z plikami konfiguracyjnymi (.txt/.ini) poprzez GUI:
    przeglądanie, wczytywanie, edycję w QTextEdit, zapisywanie oraz uruchamianie
    symulacji z aktualnie edytowanego pliku.
    """
    def __init__(self, go_back_callback, go_to_simulation_callback, parent=None):
        """
        Konstruktor ConfigPage.

        Args:
            go_back_callback (callable): Funkcja zwrotna (callback) do wywołania
                                         po kliknięciu przycisku "Powrót".
            go_to_simulation_callback (callable): Funkcja zwrotna do wywołania
                                                po kliknięciu przycisku "Uruchom symulację",
                                                przekazująca ścieżkę do aktualnego
                                                pliku konfiguracyjnego.
            parent (QWidget | None): Obiekt nadrzędny (domyślnie None).
        """
        super().__init__(parent)
        self.go_back_callback = go_back_callback
        self.go_to_simulation_callback = go_to_simulation_callback
        self.current_config_path = ""

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20,20,20,20)

        title_label = QLabel("Edytor Pliku Konfiguracyjnego")
        title_label.setObjectName("PageTitleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # Ścieżka do pliku i przycisk przeglądania
        file_bar_layout = QHBoxLayout()
        self.path_display_label = QLabel("Nie załadowano pliku")
        self.path_display_label.setStyleSheet("color: #A09CC9; font-style: italic;")
        file_bar_layout.addWidget(self.path_display_label, stretch=1)
        
        browse_btn = QPushButton("Przeglądaj plik...")
        browse_btn.clicked.connect(self.browse_file)
        file_bar_layout.addWidget(browse_btn)
        main_layout.addLayout(file_bar_layout)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Tutaj pojawi się zawartość pliku konfiguracyjnego...\nMożesz edytować tekst bezpośrednio.")
        main_layout.addWidget(self.editor, stretch=1)

        # Przyciski akcji
        action_buttons_layout = QHBoxLayout()
        action_buttons_layout.setSpacing(15)

        self.load_default_btn = QPushButton("Załaduj domyślny")
        self.load_default_btn.clicked.connect(self.load_default_config_content)
        action_buttons_layout.addWidget(self.load_default_btn)

        self.save_btn = QPushButton("Zapisz zmiany")
        self.save_btn.clicked.connect(self.save_config)
        action_buttons_layout.addWidget(self.save_btn)
        
        self.save_as_btn = QPushButton("Zapisz jako...")
        self.save_as_btn.clicked.connect(self.save_config_as)
        action_buttons_layout.addWidget(self.save_as_btn)
        main_layout.addLayout(action_buttons_layout)

        # Przyciski nawigacyjne
        nav_buttons_layout = QHBoxLayout()
        nav_buttons_layout.addStretch()

        back_btn = QPushButton("Powrót")
        back_btn.clicked.connect(self.go_back_callback)
        nav_buttons_layout.addWidget(back_btn)

        self.run_simulation_btn = QPushButton("Uruchom symulację z tym plikiem")
        self.run_simulation_btn.clicked.connect(self.run_simulation)
        self.run_simulation_btn.setEnabled(False) # Aktywny po załadowaniu/zapisaniu pliku
        nav_buttons_layout.addWidget(self.run_simulation_btn)
        main_layout.addLayout(nav_buttons_layout)

    def browse_file(self):
        """
        Otwiera okno dialogowe wyboru pliku, umożliwiając użytkownikowi
        wybranie pliku konfiguracyjnego (.txt lub .ini) do załadowania.
        """
        config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config'))
        os.makedirs(config_dir, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Wybierz plik konfiguracyjny", config_dir, "Pliki konfiguracyjne (*.txt *.ini)")
        if path:
            self.load_file_content(path)

    def load_file_content(self, file_path):
        """
        Wczytuje zawartość pliku o podanej ścieżce do edytora tekstowego.

        Aktualizuje ścieżkę bieżącego pliku i etykietę wyświetlającą nazwę pliku.
        Włącza przycisk uruchomienia symulacji.

        Args:
            file_path (str): Ścieżka do pliku konfiguracyjnego do załadowania.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.editor.setPlainText(f.read())
            self.current_config_path = file_path
            self.path_display_label.setText(f"Edytowany plik: {os.path.basename(file_path)}")
            self.run_simulation_btn.setEnabled(True)
            QMessageBox.information(self, "Sukces", f"Załadowano plik: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Błąd wczytywania", f"Nie można otworzyć pliku {file_path}:\n{e}")
            self.current_config_path = ""
            self.path_display_label.setText("Błąd ładowania pliku.")
            self.run_simulation_btn.setEnabled(False)

    def load_default_config_content(self):
        """
        Wczytuje zawartość domyślnego pliku konfiguracyjnego do edytora.

        Jeśli domyślny plik nie istnieje w oczekiwanej lokalizacji, próbuje go utworzyć.
        """
        default_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config', 'default_simulation_config.txt'))
        if not os.path.exists(default_path):
            try:
                from utils.config_parser import create_default_config
                create_default_config(default_path)
                QMessageBox.information(self, "Informacja", f"Utworzono domyślny plik konfiguracyjny w:\n{default_path}")
            except Exception as e:
                QMessageBox.warning(self, "Błąd", f"Nie można utworzyć domyślnego pliku konfiguracyjnego:\n{e}")
                return
        self.load_file_content(default_path)


    def save_config(self):
        """
        Zapisuje aktualną zawartość edytora tekstowego do bieżącego pliku.

        Jeśli nie ma ustawionej ścieżki bieżącego pliku (`self.current_config_path`),
        przekierowuje do metody `save_config_as()` w celu wybrania nowej ścieżki.

        Returns:
            bool: True, jeśli zapis zakończył się sukcesem; False w przeciwnym przypadku.
        """
        if not self.current_config_path:
            QMessageBox.warning(self, "Błąd zapisu", "Najpierw załaduj lub 'Zapisz jako...' nowy plik.")
            return self.save_config_as()

        try:
            with open(self.current_config_path, 'w', encoding='utf-8') as f:
                f.write(self.editor.toPlainText())
            QMessageBox.information(self, "Sukces", f"Zapisano zmiany w: {self.current_config_path}")
            self.run_simulation_btn.setEnabled(True)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Błąd zapisu", f"Nie można zapisać pliku {self.current_config_path}:\n{e}")
            return False

    def save_config_as(self):
        """
        Otwiera okno dialogowe zapisu pliku, umożliwiając użytkownikowi
        wybranie nowej ścieżki i nazwy pliku do zapisu aktualnej konfiguracji.

        Po wybraniu ścieżki, ustawia ją jako bieżącą ścieżkę pliku
        i wywołuje metodę `save_config()` w celu dokonania rzeczywistego zapisu.

        Returns:
            bool: True, jeśli plik został pomyślnie zapisany; False w przeciwnym przypadku
                  (np. użytkownik anulował dialog zapisu lub wystąpił błąd zapisu).
        """
        config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config'))
        path, _ = QFileDialog.getSaveFileName(self, "Zapisz plik konfiguracyjny jako...", config_dir, "Pliki konfiguracyjne (*.txt *.ini)")
        if path:
            self.current_config_path = path
            self.path_display_label.setText(f"Zapisywany plik: {os.path.basename(path)}")
            return self.save_config()
        return False

    @Slot()
    def run_simulation(self):
        """
        Slot wywoływany po kliknięciu przycisku "Uruchom symulację z tym plikiem".

        Sprawdza, czy istnieje prawidłowa ścieżka do pliku konfiguracyjnego.
        Pyta użytkownika, czy chce zapisać ewentualne niezapisane zmiany przed
        uruchomieniem symulacji. W przypadku potwierdzenia, próbuje zapisać plik.
        Jeśli plik został pomyślnie zapisany (lub użytkownik zrezygnował z zapisu),
        wywołuje callback `go_to_simulation_callback`, przekazując ścieżkę
        do bieżącego pliku konfiguracyjnego.
        """
        if not self.current_config_path or not os.path.exists(self.current_config_path):
            QMessageBox.warning(self, "Błąd", "Nie wybrano prawidłowego pliku konfiguracyjnego.")
            return

        reply = QMessageBox.question(self, "Zapisać zmiany?",
                                     "Czy chcesz zapisać zmiany w edytorze przed uruchomieniem symulacji?",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)

        if reply == QMessageBox.Cancel:
            return
        if reply == QMessageBox.Save:
            if not self.save_config():
                return

        self.go_to_simulation_callback(self.current_config_path)