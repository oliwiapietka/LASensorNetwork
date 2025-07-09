# ui/landing_page.py
"""
Moduł definiujący stronę startową (Landing Page) interfejsu GUI.

Jest to pierwszy widok, który użytkownik widzi po uruchomieniu aplikacji.
Zawiera przyciski umożliwiające przejście do konfiguracji symulacji
(wczytanie z pliku, użycie domyślnych lub ręczna konfiguracja).
Moduł zawiera również pomocniczy widget do rysowania gradientowego tła.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QSpacerItem, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

class GradientBackgroundWidget(QWidget):
    """
    Pomocniczy widget do rysowania gradientowego tła.

    Może być użyty jako tło dla innych widgetów lub okien.
    """
    def __init__(self, start_color, end_color, parent=None):
        """
        Konstruktor GradientBackgroundWidget.

        Args:
            start_color (str): Kolor początkowy gradientu (np. "#RRGGBB" lub nazwa koloru).
            end_color (str): Kolor końcowy gradientu.
            parent (QWidget | None): Obiekt nadrzędny (domyślnie None).
        """
        super().__init__(parent)
        self.start_color = QColor(start_color)
        self.end_color = QColor(end_color)
        self.setMinimumSize(200,100)

class LandingPage(QWidget):
    """
    Widget reprezentujący stronę startową aplikacji GUI.

    Wyświetla tytuł aplikacji i przyciski nawigacyjne, które pozwalają
    użytkownikowi wybrać sposób konfiguracji symulacji (wczytanie z pliku,
    domyślna konfiguracja, ręczna konfiguracja parametrów).
    """
    def __init__(self, go_to_config_callback, go_to_manual_callback, parent=None):
        """
        Konstruktor LandingPage.

        Args:
            go_to_config_callback (callable): Funkcja zwrotna (callback) do wywołania,
                                             gdy użytkownik wybierze opcję wczytania
                                             konfiguracji z pliku lub użycia domyślnej.
                                             Ta funkcja powinna przyjmować argument boolean
                                             `load_default` (True dla domyślnej, False dla pliku).
            go_to_manual_callback (callable): Funkcja zwrotna do wywołania, gdy użytkownik
                                              wybierze opcję ręcznej konfiguracji parametrów.
            parent (QWidget | None): Obiekt nadrzędny (domyślnie None).
        """
        super().__init__(parent)

        self.go_to_config_callback = go_to_config_callback
        self.go_to_manual_callback = go_to_manual_callback

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(60, 40, 60, 60) 
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.setSpacing(25)

        main_layout.addSpacerItem(QSpacerItem(20, 60, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        title_label = QLabel("Symulator Sieci Sensorowej")
        title_label.setObjectName("PageTitleLabel") 
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        main_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        btn_width = 380
        btn_height = 55

        self.load_config_btn = QPushButton("Wczytaj konfigurację z pliku")
        self.load_config_btn.setFixedSize(btn_width, btn_height)

        self.load_config_btn.clicked.connect(lambda: self.go_to_config_callback(load_default=False))
        main_layout.addWidget(self.load_config_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        main_layout.addSpacing(15)

        self.default_config_btn = QPushButton("Użyj konfiguracji domyślnej")
        self.default_config_btn.setFixedSize(btn_width, btn_height)
        self.default_config_btn.clicked.connect(lambda: self.go_to_config_callback(load_default=True))
        main_layout.addWidget(self.default_config_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        main_layout.addSpacing(15)

        self.manual_config_btn = QPushButton("Skonfiguruj parametry ręcznie")
        self.manual_config_btn.setFixedSize(btn_width, btn_height)
        self.manual_config_btn.clicked.connect(self.go_to_manual_callback)
        main_layout.addWidget(self.manual_config_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        main_layout.addSpacerItem(QSpacerItem(20, 80, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
