# ui/manual_settings_page.py
"""
Moduł definiujący stronę GUI umożliwiającą ręczną konfigurację parametrów symulacji.

Użytkownik może modyfikować różne ustawienia symulacji za pomocą pól
wejściowych (spinbox, combobox, lineedit) zorganizowanych w zakładkach.
Strona umożliwia zebranie tych ustawień, zapisanie ich do tymczasowego
pliku konfiguracyjnego i przekazanie ścieżki do tego pliku
stronie symulacji w celu jej uruchomienia.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget,
                             QLabel, QFormLayout, QSpinBox, QDoubleSpinBox, QComboBox,
                             QCheckBox, QGroupBox, QLineEdit, QMessageBox)
from PySide6.QtCore import Qt, Slot
import configparser
import os
import tempfile

class ManualSettingsPage(QWidget):
    """
    Widget reprezentujący stronę ręcznej konfiguracji parametrów symulacji.

    Umożliwia użytkownikowi wprowadzanie wartości parametrów w różnych
    sekcjach (zakładkach) i uruchomienie symulacji z tymi ustawieniami.
    Generuje plik konfiguracyjny na podstawie wprowadzonych danych.
    """
    def __init__(self, go_back_callback, go_to_simulation_callback, parent=None):
        """
        Konstruktor ManualSettingsPage.

        Args:
            go_back_callback (callable): Funkcja zwrotna (callback) do wywołania
                                         po kliknięciu przycisku "Powrót".
            go_to_simulation_callback (callable): Funkcja zwrotna do wywołania
                                                po kliknięciu przycisku "Uruchom symulację",
                                                przekazująca ścieżkę do wygenerowanego
                                                pliku konfiguracyjnego.
            parent (QWidget | None): Obiekt nadrzędny (domyślnie None).
        """
        super().__init__(parent)
        self.go_back_callback = go_back_callback
        self.go_to_simulation_callback = go_to_simulation_callback

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20,20,20,20)

        title_label = QLabel("Ręczna Konfiguracja Parametrów Symulacji")
        title_label.setObjectName("PageTitleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, stretch=1)

        # Dodawanie zakładek
        self._create_general_tab()
        self._create_network_logic_tab()
        self._create_sensor_defaults_tab()
        self._create_sensors_list_tab()
        self._create_pois_list_tab()
        self._create_communication_tab()
        self._create_faults_tab()
        self._create_deployment_optimizer_tab()

        # Przyciski nawigacyjne
        nav_buttons_layout = QHBoxLayout()
        nav_buttons_layout.addStretch()

        back_btn = QPushButton("Powrót")
        back_btn.clicked.connect(self.go_back_callback)
        nav_buttons_layout.addWidget(back_btn)

        self.run_simulation_btn = QPushButton("Uruchom symulację z tymi ustawieniami")
        self.run_simulation_btn.clicked.connect(self.prepare_and_run_simulation)
        nav_buttons_layout.addWidget(self.run_simulation_btn)
        main_layout.addLayout(nav_buttons_layout)

        # Załaduj wartości domyślne lub z ostatniej konfiguracji
        self.load_default_values()

    def _create_widget_for_section(self, section_name: str, config_options: dict):
        """
        Tworzy QGroupBox zawierający pola wejściowe (widgety) dla danej sekcji konfiguracji.

        Args:
            section_name (str): Nazwa sekcji konfiguracji (używana jako tytuł GroupBox).
            config_options (dict): Słownik definiujący opcje konfiguracyjne w tej sekcji.
                                   Format: {klucz_config: {label: str, type: str, default: any, ...}}

        Returns:
            tuple[QGroupBox, dict]: Para: utworzony QGroupBox oraz słownik
                                    {klucz_config: obiekt_widget}, mapujący klucze
                                    konfiguracji na odpowiadające im widgety.
        """
        group_box = QGroupBox(section_name)
        form_layout = QFormLayout(group_box)
        
        widgets = {}
        for key, details in config_options.items():
            label = QLabel(f"{details.get('label', key.replace('_', ' ').title())}:")
            widget_type = details.get('type', 'str')
            default_value = details.get('default')
            options = details.get('options')

            if widget_type == 'int':
                widget = QSpinBox()
                if 'range' in details: widget.setRange(details['range'][0], details['range'][1])
                if default_value is not None: widget.setValue(int(default_value))
            elif widget_type == 'float':
                widget = QDoubleSpinBox()
                if 'range' in details: widget.setRange(details['range'][0], details['range'][1])
                if 'decimals' in details: widget.setDecimals(details['decimals'])
                if default_value is not None: widget.setValue(float(default_value))
            elif widget_type == 'bool':
                widget = QComboBox()
                widget.addItems(["True", "False"])
                if default_value is not None: widget.setCurrentText(str(default_value))
            elif widget_type == 'choice' and options:
                widget = QComboBox()
                widget.addItems(options)
                if default_value is not None: widget.setCurrentText(str(default_value))
            else:
                widget = QLineEdit()
                if default_value is not None: widget.setText(str(default_value))
            
            form_layout.addRow(label, widget)
            widgets[key] = widget
        return group_box, widgets

    def _create_general_tab(self):
        """
        Tworzy zakładkę "Ogólne" z polami do konfiguracji ogólnych parametrów symulacji.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        options = {
            'area_width': {'type': 'int', 'default': 100, 'range': [10, 1000], 'label': 'Szerokość Obszaru'},
            'area_height': {'type': 'int', 'default': 100, 'range': [10, 1000], 'label': 'Wysokość Obszaru'},
            'max_rounds': {'type': 'int', 'default': 500, 'range': [1, 10000], 'label': 'Maksymalna Liczba Rund'},
            'sink_id': {'type': 'int', 'default': 0, 'range': [0, 999], 'label': 'Id Stacji Bazowej'},
            'seed': {'type': 'int', 'default': 42, 'range': [0, 10000], 'label': 'Ziarno Losowości'},
        }
        group_box, self.general_widgets = self._create_widget_for_section("Ustawienia Ogólne", options)
        layout.addWidget(group_box)
        layout.addStretch()
        self.tabs.addTab(tab, "Ogólne")

    def _create_sensors_list_tab(self):
        """
        Tworzy zakładkę "Sensory" z polem do ustawienia ogólnej liczby sensorów.
        Informuje użytkownika, że dokładne pozycje ustawia się w pliku konfiguracyjnym.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Jeżeli chcesz ustawić dokładne położenia sensorów, skorzystaj z opcji konfiguracji ''Wczytaj konfigurację z pliku''."))
        self.num_sensors_spinbox_sl = QSpinBox()
        self.num_sensors_spinbox_sl.setRange(1,100)
        self.num_sensors_spinbox_sl.setValue(30)
        f_layout = QFormLayout()
        f_layout.addRow("Liczba sensorów: ", self.num_sensors_spinbox_sl)
        layout.addLayout(f_layout)
        layout.addStretch()
        self.tabs.addTab(tab, "Sensory")

    def _create_pois_list_tab(self):
        """
        Tworzy zakładkę "Punkty POI" z polem do ustawienia ogólnej liczby POI.
        Informuje użytkownika, że dokładne pozycje ustawia się w pliku konfiguracyjnym.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Jeżeli chcesz ustawić dokładne położenia POI, skorzystaj z opcji konfiguracji ''Wczytaj konfigurację z pliku''."))
        self.num_pois_spinbox_pl = QSpinBox()
        self.num_pois_spinbox_pl.setRange(0,100)
        self.num_pois_spinbox_pl.setValue(3)
        f_layout = QFormLayout()
        f_layout.addRow("Liczba POI: ", self.num_pois_spinbox_pl)
        layout.addLayout(f_layout)
        layout.addStretch()
        self.tabs.addTab(tab, "Punkty POI")
        
    def _create_network_logic_tab(self):
        """
        Tworzy zakładkę "Logika Sieci" z polami do konfiguracji parametrów
        związanych z algorytmami sieciowymi i kryteriami zakończenia symulacji.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        options = {
            'reward_method': {'type': 'choice', 'default': 'cardinality', 'options': ['cardinality', 'energy'], 'label': 'Metoda Nagradzania'},
            'cover_set_working_time_slice': {'type': 'float', 'default': 0.5, 'range': [0.01, 5.0], 'decimals': 2, 'label': 'Czas Pracy Zbioru Pokrycia'},
            'end_condition': {'type': 'choice', 'default': 'all_sensors_dead', 
                              'options': ['all_sensors_dead', 'no_coverage', 'max_rounds_reached', 'q_coverage_threshold'], 'label': 'Warunek Zakończenia'},
        }
        group_box, self.network_logic_widgets = self._create_widget_for_section("Logika Sieci", options)
        layout.addWidget(group_box)
        layout.addStretch()
        self.tabs.addTab(tab, "Logika Sieci")

    def _create_sensor_defaults_tab(self):
        """
        Tworzy zakładkę "Domyślne Sensory" z polami do konfiguracji domyślnych
        parametrów sensorów (energia początkowa, zasięgi, parametr LA).
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        options = {
            'initial_energy': {'type': 'float', 'default': 6.0, 'range': [0.1, 10000.0], 'decimals': 1, 'label': 'Początkowa Energia'},
            'comm_range': {'type': 'int', 'default': 50, 'range': [1, 500], 'label': 'Zasięg Komunikacji'},
            'sensing_range': {'type': 'int', 'default': 20, 'range': [1, 250], 'label': 'Zasięg Sensora'},
            'la_param_a': {'type': 'float', 'default': 0.1, 'range': [0.001, 1.0], 'decimals': 3, 'label': 'Parametr A (LA)'},
        }
        group_box, self.sensor_defaults_widgets = self._create_widget_for_section("Domyślne Ustawienia Sensorów", options)
        layout.addWidget(group_box)
        layout.addStretch()
        self.tabs.addTab(tab, "Domyślne Sensory")

    def _create_communication_tab(self):
        """
        Tworzy zakładkę "Komunikacja" z polami do konfiguracji parametrów
        modelu komunikacji (utrata pakietu, opóźnienie, interwał broadcastu).
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        options = {
            'packet_loss_probability': {'type': 'float', 'default': 0.1, 'range': [0.0, 1.0], 'decimals': 3, 'label': 'Prawdopodobieństwo Utraty Pakietu'},
            'transmission_delay_per_hop': {'type': 'float', 'default': 0.1, 'range': [0.0, 5.0], 'decimals': 2, 'label': 'Opóźnienie Transmisji na Skok'},
            'max_queue_size': {'type': 'int', 'default': 10, 'range': [1, 100], 'label': 'Maksymalny Rozmiar Kolejki'},
            'poi_broadcast_interval': {'type': 'int', 'default': 5, 'range': [1, 100], 'label': 'Interwał Broadcastu POI'},
        }
        group_box, self.communication_widgets = self._create_widget_for_section("Komunikacja", options)
        layout.addWidget(group_box)
        layout.addStretch()
        self.tabs.addTab(tab, "Komunikacja")

    def _create_faults_tab(self):        
        """
        Tworzy zakładkę "Awarie" z polami do konfiguracji parametrów
        modelu awarii sensorów.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        options = {
            'sensor_failure_rate_per_round': {'type': 'float', 'default': 0.0, 'range': [0.0, 0.1], 'decimals': 4, 'label': 'Współczynnik Awarii na Rundę'},
        }
        group_box, self.faults_widgets = self._create_widget_for_section("Awarie", options)
        layout.addWidget(group_box)
        layout.addStretch()
        self.tabs.addTab(tab, "Awarie")

    def _create_deployment_optimizer_tab(self):
        """
        Tworzy zakładkę "Optymalizacja Rozmieszczenia" z polami do konfiguracji
        parametrów Algorytmu Genetycznego (GA) do optymalizacji rozmieszczenia sensorów.
        """
        tab = QWidget()
        layout = QVBoxLayout(tab)
        options = {
            'enabled': {'type': 'bool', 'default': True, 'label': 'Włączony'},
            'population_size': {'type': 'int', 'default': 20, 'range': [10, 200], 'label': 'Rozmiar Populacji'},
            'generations': {'type': 'int', 'default': 30, 'range': [5, 500], 'label': 'Liczba Pokoleń'},
            'mutation_rate': {'type': 'float', 'default': 0.1, 'range': [0.0, 1.0], 'decimals': 2, 'label': 'Współczynnik Mutacji'},
            'crossover_rate': {'type': 'float', 'default': 0.7, 'range': [0.0, 1.0], 'decimals': 2, 'label': 'Współczynnik Krzyżowania'},
            'tournament_size': {'type': 'int', 'default': 3, 'range': [2, 10], 'label': 'Rozmiar Turnieju'},
            'elitism_count': {'type': 'int', 'default': 1, 'range': [0, 5], 'label': 'Rozmiar Elity'},
        }
        group_box, self.optimizer_widgets = self._create_widget_for_section("Optymalizator Rozmieszczenia (GA)", options)
        layout.addWidget(group_box)
        layout.addStretch()
        self.tabs.addTab(tab, "Optymalizacja Rozmieszczenia")


    def load_default_values(self):
        """
        Wczytuje domyślne wartości parametrów z pliku konfiguracyjnego
        'config/default_simulation_config.txt' i ustawia je w odpowiednich
        polach wejściowych GUI.

        Jeśli domyślny plik konfiguracyjny nie istnieje, próbuje go utworzyć.
        """
        default_config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config', 'default_simulation_config.txt'))
        if not os.path.exists(default_config_path):
            from utils.config_parser import create_default_config
            create_default_config(default_config_path)

        parser = configparser.ConfigParser()
        parser.read(default_config_path)

        self._set_widget_values(parser, 'General', self.general_widgets)
        self._set_widget_values(parser, 'NetworkLogic', self.network_logic_widgets)
        self._set_widget_values(parser, 'SensorDefaults', self.sensor_defaults_widgets)
        self._set_widget_values(parser, 'Communication', self.communication_widgets)
        self._set_widget_values(parser, 'Faults', self.faults_widgets)
        self._set_widget_values(parser, 'DeploymentOptimizer', self.optimizer_widgets)
        
        if parser.has_section('Sensors'):
            self.num_sensors_spinbox_sl.setValue(parser.getint('Sensors', 'count', fallback=30))
        if parser.has_section('POIs'):
            self.num_pois_spinbox_pl.setValue(parser.getint('POIs', 'count', fallback=3))


    def _set_widget_values(self, parser, section, widgets_dict):
        """
        Ustawia wartości w widgetach na podstawie danych z parsera konfiguracji.

        Args:
            parser (configparser.ConfigParser): Obiekt parsera z wczytaną konfiguracją.
            section (str): Nazwa sekcji konfiguracji.
            widgets_dict (dict): Słownik {klucz_config: obiekt_widget} dla tej sekcji.
        """
        if not parser.has_section(section):
            return
        for key, widget in widgets_dict.items():
            if parser.has_option(section, key):
                value_str = parser.get(section, key)
                if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                    try: widget.setValue(float(value_str) if '.' in value_str else int(value_str))
                    except ValueError: pass
                elif isinstance(widget, QComboBox):
                    widget.setCurrentText(value_str)
                elif isinstance(widget, QLineEdit):
                    widget.setText(value_str)
                elif isinstance(widget, QCheckBox):
                    widget.setChecked(parser.getboolean(section, key))


    def _get_widget_values(self, parser, section, widgets_dict):
        """
        Pobiera wartości z widgetów i zapisuje je w obiekcie parsera konfiguracji.

        Args:
            parser (configparser.ConfigParser): Obiekt parsera, do którego zostaną
                                               zapisane wartości.
            section (str): Nazwa sekcji konfiguracji.
            widgets_dict (dict): Słownik {klucz_config: obiekt_widget} dla tej sekcji.
        """
        if not parser.has_section(section):
            parser.add_section(section)
        for key, widget in widgets_dict.items():
            if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                parser.set(section, key, str(widget.value()))
            elif isinstance(widget, QComboBox):
                parser.set(section, key, widget.currentText())
            elif isinstance(widget, QLineEdit):
                parser.set(section, key, widget.text())
            elif isinstance(widget, QCheckBox):
                 parser.set(section, key, str(widget.isChecked()))

    @Slot()
    def prepare_and_run_simulation(self):
        """
        Slot wywoływany po kliknięciu przycisku "Uruchom symulację z tymi ustawieniami".

        Zbiera wszystkie parametry z pól wejściowych GUI, tworzy obiekt
        configparser z tymi danymi, zapisuje konfigurację do tymczasowego
        pliku i wywołuje callback `go_to_simulation_callback`, przekazując
        ścieżkę do tego tymczasowego pliku.
        """
        # 1. Zbieranie danych z GUI
        config_out = configparser.ConfigParser()
        
        self._get_widget_values(config_out, 'General', self.general_widgets)
        self._get_widget_values(config_out, 'NetworkLogic', self.network_logic_widgets)
        self._get_widget_values(config_out, 'SensorDefaults', self.sensor_defaults_widgets)
        self._get_widget_values(config_out, 'Communication', self.communication_widgets)
        self._get_widget_values(config_out, 'Faults', self.faults_widgets)
        self._get_widget_values(config_out, 'DeploymentOptimizer', self.optimizer_widgets)

        config_out.add_section('Sensors')
        config_out.set('Sensors', 'count', str(self.num_sensors_spinbox_sl.value()))

        config_out.add_section('POIs')
        config_out.set('POIs', 'count', str(self.num_pois_spinbox_pl.value()))

        default_config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'config', 'default_simulation_config.txt'))
        default_parser = configparser.ConfigParser()
        default_parser.read(default_config_path)
        
        if default_parser.has_section('Output'):
            config_out.add_section('Output')
            for key, value in default_parser.items('Output'):
                config_out.set('Output', key, value)
        
        if default_parser.has_section('Visualization'):
            config_out.add_section('Visualization')
            for key, value in default_parser.items('Visualization'):
                config_out.set('Visualization', key, value)


        # 2. Zapis do pliku tymczasowego
        try:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.ini', encoding='utf-8') as tmp_file:
                config_out.write(tmp_file)
                temp_config_path = tmp_file.name
            
            # 3. Przekazanie ścieżki do MainWindow
            self.go_to_simulation_callback(temp_config_path)

        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie można przygotować pliku konfiguracyjnego:\n{e}")