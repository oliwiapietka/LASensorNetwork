# utils/config_parser.py
"""
Moduł do parsowania i zarządzania plikami konfiguracyjnymi symulacji.

Umożliwia wczytywanie parametrów symulacji z pliku tekstowego
w formacie INI (lub podobnym) przy użyciu modułu configparser.
Zawiera również funkcję do tworzenia domyślnego pliku konfiguracyjnego.
"""
import configparser
import os

def load_config(filepath="config/default_simulation_config.txt"):
    """
    Wczytuje konfigurację symulacji z pliku.

    Używa modułu `configparser` do odczytania danych z pliku
    o strukturze sekcji i par klucz=wartość.

    Args:
        config_file_path (str): Ścieżka do pliku konfiguracyjnego.

    Returns:
        configparser.ConfigParser: Obiekt parsera konfiguracji
                                   zawierający wczytane dane.

    Raises:
        FileNotFoundError: Jeśli plik konfiguracyjny nie istnieje.
        configparser.Error: W przypadku błędu parsowania pliku konfiguracyjnego.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Config file not found: {filepath}")
    config = configparser.ConfigParser()
    config.read(filepath)
    return config

def create_default_config(filepath="config/default_simulation_config.txt"):
    """
    Tworzy domyślny plik konfiguracyjny symulacji.

    Zapisuje standardowy zestaw parametrów do pliku o podanej ścieżce.
    Tworzy katalog docelowy, jeśli nie istnieje.

    Args:
        filepath (str): Ścieżka do pliku, w którym ma zostać zapisana
                        domyślna konfiguracja.
    """
    config = configparser.ConfigParser()

    config['General'] = {
        'area_width': '100',
        'area_height': '100',
        'max_rounds': '500',
        'sink_id': '0',
        'network_lifetime_metric': 'q_coverage_threshold',
        'min_q_coverage_threshold': '0.5'
    }
    config['SensorDefaults'] = {
        'initial_energy': '1.0',
        'comm_range': '25',
        'sensing_range': '15',
        'la_param_a': '0.1'
    }
    config['Sensors'] = {
        'count': '50',
        # Można dodać specyficzne pozycje i parametry dla każdego sensora, np.:
        # 'sensor_0_id': '0',
        # 'sensor_0_x': '50',
        # 'sensor_0_y': '50',
        # 'sensor_0_energy': '1000', # Nadpisuje domyślne
        # Jeśli nie ma specyficznych, będą losowo rozmieszczone lub wg strategii
    }
    config['POIs'] = {
        'count': '10',
        # 'poi_0_x': '20',
        # 'poi_0_y': '80',
    }
    config['Communication'] = {
        'packet_loss_probability': '0.01',
        'transmission_delay_per_hop': '0.1'
    }
    config['Faults'] = {
        'sensor_failure_rate_per_round': '0.0005'
    }
    config['Output'] = {
        'results_file': 'results/simulation_log.txt',
        'plot_directory': 'results/'
    }
    config['Visualization'] = {
        'enabled': 'True',
        'plot_interval': '1',
    }

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as configfile:
        config.write(configfile)
    print(f"Default config file created at {filepath}")

# Wywołanie, aby utworzyć plik, jeśli go nie ma
if __name__ == '__main__':
    create_default_config()