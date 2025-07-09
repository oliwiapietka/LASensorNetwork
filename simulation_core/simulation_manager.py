# simulation_core/simulation_manager.py
"""
Moduł zarządzający przebiegiem symulacji sieci sensorowej.

SimulationManager jest centralnym punktem kontrolnym symulacji.
Odpowiada za wczytanie konfiguracji, inicjalizację sieci sensorowej
(w tym potencjalną optymalizację rozmieszczenia), zarządzanie cyklem
symulacji (krok po kroku), zbieranie statystyk, wizualizację wyników
i generowanie raportów końcowych.
"""
from .network import Network
from utils.config_parser import load_config
from visualization.animator import NetworkAnimator
from visualization.plot_generator import PlotGenerator
from .sensor import SensorState
import time
import random
import logging
from utils.logger import SimulationLogger
from .deployment_optimizer import GADeploymentOptimizer

class SimulationManager:
    """
    Klasa zarządzająca cyklem życia i przebiegiem symulacji WSN.

    Wczytuje konfigurację, ustawia środowisko symulacji, uruchamia
    poszczególne rundy, zbiera i przetwarza statystyki oraz obsługuje
    wizualizację i raportowanie końcowe.
    """
    def __init__(self, config_file_path):
        """
        Konstruktor klasy SimulationManager.

        Wczytuje konfigurację z podanego pliku i inicjalizuje niezbędne
        komponenty symulacji, takie jak logger.

        Args:
            config_file_path (str): Ścieżka do pliku konfiguracyjnego symulacji.
        """
        self.config = load_config(config_file_path)
        self.network: Network | None = None
        self.logger = SimulationLogger(self.config.get("Output", "results_file", fallback="results/simulation_log.txt"))
        self.animator = None
        self.all_stats = []

    def _run_deployment_optimization(self) -> list[dict] | None:
        """
        Uruchamia optymalizację rozmieszczenia sensorów przy użyciu Algorytmu Genetycznego (GA), jeśli jest włączona w konfiguracji.

        Przygotowuje parametry dla optymalizatora GA na podstawie pliku konfiguracyjnego.
        Jeśli optymalizacja jest włączona, tworzy instancję GADeploymentOptimizer
        i uruchamia proces optymalizacji.

        Returns:
            list[dict] | None: Lista słowników zoptymalizowanych współrzędnych dla
                               każdego sensora (format: [{'id': ..., 'x': ..., 'y': ..., 'is_sink_role': ...}, ...])
                               lub None, jeśli optymalizacja jest wyłączona lub wystąpił błąd.
        """
        if not self.config.getboolean('DeploymentOptimizer', 'enabled', fallback=False):
            logging.info("Deployment optimization is disabled in config.")
            return None

        ga_config_params = self.config['DeploymentOptimizer']
        network_layout_config = self.config['General']
        sensor_default_params = self.config['SensorDefaults']

        # Przygotuj konfiguracje POI dla optymalizatora
        # GA potrzebuje znać POI do oceny funkcji celu
        poi_initial_configs = []
        num_pois_cfg = self.config.getint('POIs', 'count', fallback=0)
        for i in range(num_pois_cfg):
            poi_initial_configs.append({
                'id': self.config.getint('POIs', f'poi_{i}_id', fallback=i),
                'x': self.config.getfloat('POIs', f'poi_{i}_x', fallback=random.uniform(0, network_layout_config.getfloat('area_width'))),
                'y': self.config.getfloat('POIs', f'poi_{i}_y', fallback=random.uniform(0, network_layout_config.getfloat('area_height'))),
            })
        
        num_sensors_total_from_config = self.config.getint('Sensors', 'count')
        sink_id_from_config = self.config.getint('General', 'sink_id')

        optimizer = GADeploymentOptimizer(
            ga_config_params=ga_config_params,
            network_layout_config=network_layout_config,
            sensor_default_params=sensor_default_params,
            poi_initial_configs=poi_initial_configs,
            k_coverage_target=self.config.getint("NetworkLogic", "target_k_coverage", fallback=1),
            num_sensors_total=num_sensors_total_from_config,
            sink_id_to_assign=sink_id_from_config # Przekaż sink_id z config jako indeks dla GA
        )
        
        optimized_coords_list = optimizer.run_optimization() # zwraca listę słowników z 'id', 'x', 'y', 'is_sink_role'
        return optimized_coords_list


    def _setup_simulation(self):
        """
        Konfiguruje początkowy stan symulacji.

        Wczytuje parametry sieci, sensorów i POI z pliku konfiguracyjnego,
        opcjonalnie uruchamia optymalizację rozmieszczenia, tworzy obiekt
        Network i rozmieszcza w nim sensory i POI. Inicjalizuje animatora,
        jeśli wizualizacja jest włączona.
        """
        logging.info("Starting simulation setup...")
        # Krok 1: Uruchomienie optymalizacji rozmieszczenia (jeśli włączona)
        # Wynik optymalizacji (lista zoptymalizowanych pozycji) będzie użyty do rozmieszczenia sensorów.
        optimized_deployment_coords = self._run_deployment_optimization()
        
        # Krok 2: Inicjalizacja obiektu Network
        general_cfg = self.config['General']
        network_logic_cfg = self.config['NetworkLogic']
        communication_cfg = self.config['Communication']
        faults_cfg = self.config['Faults']
        sensor_defaults_cfg = self.config['SensorDefaults']
        
        self.network = Network(
            width=general_cfg.getfloat('area_width'),
            height=general_cfg.getfloat('area_height'),
            sink_id=general_cfg.getint('sink_id'),  # To ID będzie używane do identyfikacji sinka
            config=self.config,
            packet_loss_prob=communication_cfg.getfloat("packet_loss_probability", fallback=0.01),
            sensor_failure_prob_per_round=faults_cfg.getfloat("sensor_failure_rate_per_round", fallback=0.001),
            la_param_a=sensor_defaults_cfg.getfloat("la_param_a", fallback=0.1),
            reward_method=network_logic_cfg.get("reward_method", fallback="cardinality")
        )

        # Krok 3: Przygotowanie konfiguracji sensorów do rozmieszczenia
        sensor_configs = []
        num_sensors_cfg = self.config.getint('Sensors', 'count')
        default_energy = sensor_defaults_cfg.getfloat('initial_energy')
        default_comm_range = sensor_defaults_cfg.getfloat('comm_range')
        default_sensing_range = sensor_defaults_cfg.getfloat('sensing_range')
        default_la_param_a = sensor_defaults_cfg.getfloat('la_param_a')
        sink_id_cfg = general_cfg.getint('sink_id')


        if optimized_deployment_coords:
            logging.info("Using optimized deployment coordinates from GA.")
            
            for i in range(num_sensors_cfg):
                # Znajdź dane dla sensora o GA-indeksie `i` z wyniku optymalizacji
                opt_coords_for_sensor_i = next((item for item in optimized_deployment_coords if item['id'] == i), None)
                if not opt_coords_for_sensor_i:
                    logging.error(f"Could not find optimized coordinates for GA-indexed sensor {i}. Using defaults/random.")
                     # Fallback na domyślne/losowe, jeśli nie znaleziono zoptymalizowanej pozycji
                    opt_x = random.uniform(0, general_cfg.getfloat('area_width'))
                    opt_y = random.uniform(0, general_cfg.getfloat('area_height'))
                else:
                    opt_x = opt_coords_for_sensor_i['x']
                    opt_y = opt_coords_for_sensor_i['y']

                sensor_actual_id = self.config.getint('Sensors', f'sensor_{i}_id', fallback=i)
                
                # Przygotowanie konfiguracji dla pojedynczego sensora
                s_conf = {
                    'id': sensor_actual_id, # Rzeczywiste ID sensora
                    'x': opt_x,
                    'y': opt_y,
                    # Odczytaj specyficzne parametry z config, jeśli istnieją, inaczej default
                    'initial_energy': self.config.getfloat('Sensors', f'sensor_{sensor_actual_id}_initial_energy', fallback=default_energy),
                    'comm_range': self.config.getfloat('Sensors', f'sensor_{sensor_actual_id}_comm_range', fallback=default_comm_range),
                    'sensing_range': self.config.getfloat('Sensors', f'sensor_{sensor_actual_id}_sensing_range', fallback=default_sensing_range),
                    'la_param_a': self.config.getfloat('Sensors', f'sensor_{sensor_actual_id}_la_param_a', fallback=default_la_param_a),
                }
                sensor_configs.append(s_conf)
        else:
            logging.info("Using deployment coordinates from configuration file (or random for unspecified).")
            # Logika wczytywania/losowania pozycji, jeśli optymalizacja nie była włączona lub zawiodła
            for i in range(num_sensors_cfg):
                # Rzeczywiste ID sensora
                sensor_actual_id = self.config.getint('Sensors', f'sensor_{i}_id', fallback=i)
                
                s_conf = {
                    'id': sensor_actual_id,
                    # Wczytaj pozycję z configu lub wylosuj, jeśli nie zdefiniowana
                    'x': self.config.getfloat('Sensors', f'sensor_{sensor_actual_id}_x', fallback=random.uniform(0, general_cfg.getfloat('area_width'))),
                    'y': self.config.getfloat('Sensors', f'sensor_{sensor_actual_id}_y', fallback=random.uniform(0, general_cfg.getfloat('area_height'))),
                    'initial_energy': self.config.getfloat('Sensors', f'sensor_{sensor_actual_id}_initial_energy', fallback=default_energy),
                    'comm_range': self.config.getfloat('Sensors', f'sensor_{sensor_actual_id}_comm_range', fallback=default_comm_range),
                    'sensing_range': self.config.getfloat('Sensors', f'sensor_{sensor_actual_id}_sensing_range', fallback=default_sensing_range),
                    'la_param_a': self.config.getfloat('Sensors', f'sensor_{sensor_actual_id}_la_param_a', fallback=default_la_param_a),
                }
                sensor_configs.append(s_conf)

        # Krok 4: Rozmieszczenie sensorów w sieci
        self.network.deploy_sensors(sensor_configs)
        logging.debug(f"Deployed {len(self.network.sensors)} sensors after setup.")
        # Opcjonalne logowanie końcowych pozycji sensorów
        #for s_id, s_obj in self.network.sensors.items():
        #    logging.debug(f"  Final Sensor {s_id}: Pos=({s_obj.pos[0]:.2f},{s_obj.pos[1]:.2f}), Sink={s_obj.is_sink}")

        # Krok 5: Rozmieszczenie POI
        # Wczytywanie konfiguracji POI z pliku
        poi_configs_list = []
        num_pois = self.config.getint('POIs', 'count', fallback=0)
        for i in range(num_pois):
            # Wczytaj konfigurację POI lub użyj wartości domyślnych/losowych
            p_conf = {
                'id': self.config.getint('POIs', f'poi_{i}_id', fallback=i),
                'x': self.config.getfloat('POIs', f'poi_{i}_x', fallback=random.uniform(0, self.network.width)),
                'y': self.config.getfloat('POIs', f'poi_{i}_y', fallback=random.uniform(0, self.network.height)),
                'critical_level': self.config.getint('POIs', f'poi_{i}_critical_level', fallback=1)
            }
            poi_configs_list.append(p_conf)
        self.network.deploy_pois(poi_configs_list)

        # Krok 6: Inicjalizacja animatora wizualizacji (jeśli włączony)
        if self.config.getboolean("Visualization", "enabled", fallback=False):
            self.animator = NetworkAnimator(self.network,
                                            plot_interval=self.config.getint("Visualization", "plot_interval", fallback=1))
        logging.info("Simulation setup finished.")

    def run_simulation(self):
        """
        Uruchamia główną pętlę symulacji.

        Wykonuje kolejne rundy symulacji aż do osiągnięcia maksymalnej
        liczby rund lub spełnienia kryterium zakończenia sieci (np. utrata pokrycia).
        Zbiera statystyki z każdej rundy, loguje je i aktualizuje wizualizację.
        W trybie GUI (jeśli wywoływana przez GUI), yielduje statystyki
        po każdej rundzie, aby GUI mogło się zaktualizować.
        Na końcu generuje wykresy końcowe i zamyka logger.
        """

        # Krok 1: Konfiguracja symulacji
        self._setup_simulation()
        # Krok 2: Pobranie parametrów zakończenia symulacji z konfiguracji
        max_rounds = self.config.getint("General", "max_rounds", fallback=100)
        network_lifetime_metric = self.config.get("General", "network_lifetime_metric", fallback="all_pois_uncovered")
        min_q_coverage_threshold = self.config.getfloat("General", "min_q_coverage_threshold", fallback=0.5)

        start_time = time.time() # Czas rozpoczęcia symulacji

        for r in range(max_rounds):
            current_stats = self.network.run_one_round()

            # Sprawdzenie, czy runda zwróciła statystyki (powinna zawsze)
            if current_stats is None:
                print(f"SIM CRITICAL ERROR: network.run_one_round() returned None at round {self.network.current_round if self.network else r + 1}.")
                print("The simulation cannot continue without round statistics. Ending simulation.")
                break

            # Zapisanie statystyk bieżącej rundy
            self.all_stats.append(current_stats)

            # Oblicz metryki
            active_sensors = sum(1 for s in self.network.sensors.values() if s.state == SensorState.ACTIVE)
            inactive_sensors = sum(1 for s in self.network.sensors.values() if s.state == SensorState.SLEEP)
            dead_sensors = sum(1 for s in self.network.sensors.values() if s.state == SensorState.DEAD)
            battery_levels = {s.id: s.current_energy for s in self.network.sensors.values()}
            neighbors = {s.id: [n.id for n in s.neighbors] for s in self.network.sensors.values()}
            coverage_q = current_stats.get('coverage_q_k', 1.0)
            pdr = current_stats.get('pdr', 0.0)
            latency = current_stats.get('avg_latency', 0.0)

            # Logowanie kluczowych metryk rundy
            # Logowanie wszystkich statystyk z run_one_round jest zarządzane przez SimulationLogger
            self.logger.log_message(f"Round {r + 1} Metrics:")
            self.logger.log_message(f"Active Sensors: {active_sensors}")
            self.logger.log_message(f"Inactive Sensors: {inactive_sensors}")
            self.logger.log_message(f"Dead Sensors: {dead_sensors}")
            self.logger.log_message(f"Battery Levels: {battery_levels}")
            self.logger.log_message(f"Neighbors: {neighbors}")
            self.logger.log_message(f"Coverage Q: {coverage_q}")
            self.logger.log_message(f"PDR: {pdr}")
            self.logger.log_message(f"Latency: {latency}")

            if self.animator:
                if not self.animator.update_plot(r):
                    print("Visualization window closed. Stopping simulation.")
                    break

            yield current_stats  # Yield the current stats for GUI updates

            if self.network.coverage_lost:
                print(f"SIM END: Coverage lost at round {self.network.current_round} as reported by Network object.")
                break

            active_non_sink_sensors = current_stats.get('active_sensors', 0)
            current_q_coverage = current_stats.get('coverage_q_k', 1.0)

            # Krok 4: Aktualizacja wizualizacji (jeśli włączona)
            if network_lifetime_metric == "all_pois_uncovered" and self.network.pois:
                if current_q_coverage == 0.0:
                    print(f"SIM END: All POIs are effectively uncovered (Q={current_q_coverage:.2f}) at round {self.network.current_round}.")
                    break
            elif network_lifetime_metric == "q_coverage_threshold":
                if current_q_coverage < min_q_coverage_threshold and self.network.pois:
                    print(f"SIM END: Coverage Q ({current_q_coverage:.2f}) fell below threshold {min_q_coverage_threshold} at round {self.network.current_round}.")
                    break
            elif network_lifetime_metric == "no_active_sensors":
                if active_non_sink_sensors == 0 and len(self.network.sensors) > 1:
                    print(f"SIM END: No active non-sink sensors remaining at round {self.network.current_round}.")
                    break

            if r == max_rounds - 1:
                print(f"SIM END: Reached max rounds ({max_rounds}).")

        # Krok 7: Zakończenie symulacji
        end_time = time.time()
        simulation_duration = end_time - start_time
        print(f"Simulation finished in {simulation_duration:.2f} seconds.")

        self.logger.close()
        self._generate_final_plots()

        # Obliczenie i wyświetlenie finalnej żywotności sieci (na podstawie liczby ukończonych rund)
        final_lifetime = self.network.get_network_lifetime()
        print(f"Final Network Lifetime (rounds): {final_lifetime}")
        print(f"Results saved to: {self.logger.filepath}")
        print(f"Plots saved to directory: {self.config.get('Output', 'plot_directory', fallback='results/')}")

    def _generate_final_plots(self):
        """
        Generuje końcowe wykresy podsumowujące wyniki symulacji.

        Wykorzystuje obiekt PlotGenerator do stworzenia i zapisania wykresów
        na podstawie zebranych statystyk z wszystkich rund.
        """
        plot_dir = self.config.get("Output", "plot_directory", fallback="results/")
        plot_gen = PlotGenerator(self.all_stats, plot_dir)
        plot_gen.plot_all()