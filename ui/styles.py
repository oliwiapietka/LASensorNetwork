# ui/styles.py


MAIN_STYLESHEET = """
    QWidget {
        background-color: #0D0C1D; /* Główny bardzo ciemny fioletowo-niebieski */
        color: #E0E0E0; /* Jasny szary/biały tekst */
        font-size: 15px;
    }

    /* --- Przyciski --- */
    QPushButton {
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                  stop:0 #6C63FF, stop:1 #A084E8);
        color: white;
        border: none;
        padding: 10px 22px;
        font-size: 16px;
        font-weight: bold;
        border-radius: 8px;
        min-height: 28px;
        outline: none; /* Usuń domyślny outline przy fokusie */
    }
    QPushButton:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #9A4DFF, stop:1 #F1D5F0);
    }
    QPushButton:pressed {
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #068f81, stop:1 #837ae6);
    }
    QPushButton:disabled {
        background-color: #4A4A6A;
        color: #808080;
    }

    /* --- Etykiety --- */
    QLabel {
        color: #C0BBDD; /* Jasny lawendowy */
        background-color: transparent;
    }
    QLabel#PageTitleLabel {
        font-size: 45px;
        font-weight: bold;
        color: white;
        padding-bottom: 15px;
        padding-top: 10px;
    }
    QLabel#SectionTitleLabel {
        font-size: 16px;
        font-weight: bold;
        color: #E0E0E0;
        margin-top: 10px;
        margin-bottom: 5px;
    }

    /* --- Pola wprowadzania --- */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
        background-color: #1D1A2E;
        border: 1px solid #2D2942;
        border-radius: 8px;
        padding: 6px 10px;
        font-family: "Inter", sans-serif;
        font-size: 13px;
        color: #E0E0E0;
    }
    QTextEdit {
        selection-background-color: #7F00FF;
    }
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
        subcontrol-origin: border;
        subcontrol-position: right;
        width: 18px;
        border-left-width: 1px;
        border-left-color: #3A366B;
        border-left-style: solid;
        border-top-right-radius: 8px;
        border-bottom-right-radius: 8px;
        background-color: #3A366B;
    }
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
        image: url(assets/icons/arrow_up_light.png); /* Wskaż na ikonkę */
        width: 10px; height: 10px;
    }
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
        image: url(assets/icons/arrow_down_light.png); /* Wskaż na ikonkę */
        width: 10px; height: 10px;
    }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 20px;
        border-left-width: 1px;
        border-left-color: #3A366B;
        border-left-style: solid;
        border-top-right-radius: 8px;
        border-bottom-right-radius: 8px;
    }
    QComboBox::down-arrow {
        image: url(assets/icons/arrow_down_light.png); /* Wskaż na ikonkę */
        width: 12px; height: 12px;
    }
    QComboBox QAbstractItemView { /* Stylizacja listy rozwijanej */
        background-color: #1C1A3A;
        border: 1px solid #3A366B;
        selection-background-color: #7F00FF;
        color: #E0E0E0;
    }


    /* --- Kontenery i Grupy --- */
    QGroupBox {
        background-color: qlineargradient(spread:pad, x1:0.5, y1:0, x2:0.5, y2:1,
                                        stop:0 rgba(42, 39, 79, 200), stop:1 rgba(28, 26, 58, 220)); /* Półprzezroczysty gradient */
        border: 1px solid #3A366B;
        border-radius: 10px;
        margin-top: 1.5em; /* Zwiększone, by tytuł się zmieścił */
        padding: 10px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 5px 10px;
        margin-left: 10px;
        color: #E0E0E0;
        font-size: 14px;
        font-weight: bold;
        background-color: #7F00FF; /* Akcentowy kolor dla tła tytułu */
        border-radius: 6px;
    }

    /* --- Zakładki --- */
    QTabWidget::pane {
        border: 1px solid #3A366B;
        border-top: none;
        border-radius: 0 0 15px 15px; /* Zaokrąglenie tylko dolnych rogów panelu */
        background-color: rgba(28, 26, 58, 200);
    }
    QTabBar::tab {
        background-color: #1C1A3A;
        border: 1px solid #3A366B;
        border-bottom: none;
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        padding: 10px 20px;
        margin-right: 3px;
        color: #A09CC9;
        font-weight: bold;
    }
    QTabBar::tab:selected {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                        stop:0 #3D3875, stop:1 #2C2858);
        color: white;
        border-bottom: 2px solid #b3a6ff; /* Akcent */
    }
    QTabBar::tab:!selected:hover {
        background-color: #25214A;
    }

    /* --- Obszar wizualizacji --- */
    QGraphicsView {
        border: 1px solid #3A366B;
        border-radius: 15px;
        background-color: #16142F; /* Trochę jaśniejszy niż główne tło */
    }

    /* --- Paski przewijania --- */
    QScrollBar:vertical {
        border: none;
        background: #1C1A3A;
        width: 12px;
        margin: 15px 0 15px 0;
        border-radius: 6px;
    }
    QScrollBar::handle:vertical {
        background: #6D5BBA;
        min-height: 25px;
        border-radius: 6px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        border: none;
        background: none;
        height: 15px;
        subcontrol-position: top;
        subcontrol-origin: margin;
    }
    QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
        /* image: url(...); */
        background: none;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: none;
    }
    /* Podobnie dla QScrollBar:horizontal */
"""