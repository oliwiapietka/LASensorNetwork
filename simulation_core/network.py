# simulation_core/network.py
"""
Moduł definiujący klasę Network, reprezentującą bezprzewodową sieć sensorową (WSN).

Klasa Network zarządza kolekcją sensorów i punktów zainteresowania (POI).
Implementuje logikę przebiegu pojedynczej rundy symulacji, w tym:
- Fazę Learning (automaty uczące określają potencjalne stany)
- Fazę Monitoring (wybór zbioru pokrycia CS i sensorów mostów)
- Fazę Update (aktualizacja stanów i energii sensorów)
- Obsługę komunikacji między sensorami
- Obliczanie wskaźników takich jak pokrycie Q, PDR, opóźnienie.
"""
import random
import collections
import logging
from .sensor import Sensor, SensorState
from .poi import POI
from .communication_model import CommunicationManager, Packet
from .energy_model import EnergyConsumption

# Konfiguracja podstawowego logowania (może być nadpisana przez konfigurację w SimulationManager)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class Network:
    """
    Reprezentuje sieć sensorową.

    Zarządza sensorami, POI, przebiegiem symulacji runda po rundzie,
    komunikacją, zużyciem energii i obliczaniem kluczowych metryk wydajności sieci.
    """
    def __init__(self, width, height, sink_id, config,
                 packet_loss_prob=0.01,
                 sensor_failure_prob_per_round=0.001,
                 la_param_a=0.1,
                 reward_method="cardinality"):
        """
        Konstruktor klasy Network.

        Inicjalizuje sieć o określonych wymiarach, definiuje stację bazową (sink),
        wczytuje konfigurację i inicjalizuje menedżerów komunikacji.

        Args:
            width (float): Szerokość obszaru symulacji.
            height (float): Wysokość obszaru symulacji.
            sink_id (int): ID sensora pełniącego rolę stacji bazowej (sink).
            config (dict): Obiekt (słownik-podobny) zawierający pełną konfigurację symulacji.
            packet_loss_prob (float): Prawdopodobieństwo utraty pakietu podczas transmisji (domyślnie 0.01).
            sensor_failure_prob_per_round (float): Prawdopodobieństwo awarii sensora w każdej rundzie (domyślnie 0.001).
            la_param_a (float): Domyślny parametr uczenia 'a' dla automatów uczących (domyślnie 0.1).
            reward_method (str): Metoda obliczania nagrody dla automatów uczących ("cardinality" lub "energy") (domyślnie "cardinality").
        """
        self.width = width
        self.height = height
        self.sensors: dict[int, Sensor] = {}
        self.pois: list[POI] = []
        self.sink_node: Sensor | None = None
        self.sink_id = sink_id
        self.config = config
        
        # Inicjalizacja managerów i parametrów symulacji
        self.communication_manager = CommunicationManager(self, packet_loss_probability=packet_loss_prob)
        self.sensor_failure_prob_per_round = sensor_failure_prob_per_round
        self.current_round = 0

        # Statystyki sieci
        self.total_packets_generated = 0
        self.total_packets_delivered_to_sink = 0
        self.total_latency = 0.0

        # Parametry algorytmu uczenia LA
        self.la_param_a = la_param_a
        self.reward_method = reward_method
        
        # Progi dla metody nagradzania "cardinality" i "energy" (dynamicznie aktualizowane)
        self.min_Th_cardinality_observed = float('inf') # Dla Metody 1 Nagrody
        self.max_Eth_remaining_energy_observed = -float('inf') # Dla Metody 2 Nagrody (pozostała energia)

        self.is_first_iteration = True # Flaga dla jednorazowej inicjalizacji LA
        self.coverage_lost = False # Flaga do zakończenia symulacji, jeśli pokrycie nie może być utrzymane

        self.k_coverage_level = 1

        self.poi_broadcast_interval = config.getint("Communication", "poi_broadcast_interval", fallback=5) # Co ile rund broadcast

    def add_sensor(self, sensor_config: dict):
        """
        Dodaje pojedynczy sensor do sieci.

        Tworzy obiekt Sensor na podstawie podanej konfiguracji i dodaje go
        do wewnętrznego słownika sensorów. Jeśli sensor jest stacją bazową,
        ustawia również referencję do sink_node.

        Args:
            sensor_config (dict): Słownik zawierający konfigurację pojedynczego sensora
                                  (musi zawierać 'id', 'x', 'y', 'initial_energy',
                                  'comm_range', 'sensing_range', 'la_param_a').
        """
        # Utworzenie obiektu Sensor.
        s = Sensor(id=sensor_config['id'], x=sensor_config['x'], y=sensor_config['y'],
                   initial_energy=sensor_config['initial_energy'],
                   comm_range=sensor_config['comm_range'],
                   sensing_range=sensor_config['sensing_range'],
                   sink_id=self.sink_id,
                   learning_rate_reward_A=sensor_config['la_param_a'])
        self.sensors[s.id] = s
        # Jeśli dodany sensor jest stacją bazową, zapisz referencję
        if s.is_sink:
            self.sink_node = s

    def deploy_sensors(self, sensor_configs: list):
        """
        Rozmieszcza sensory w sieci na podstawie listy konfiguracji.

        Iteruje przez listę konfiguracji sensorów, dodaje każdy sensor do sieci,
        ograniczając jego pozycję do wymiarów obszaru symulacji. Po rozmieszczeniu
        wszystkich sensorów, odkrywa sąsiadów i monitorowane POI dla każdego z nich.

        Args:
            sensor_configs (list[dict]): Lista słowników, gdzie każdy słownik
                                         zawiera konfigurację pojedynczego sensora.
        """
        for config in sensor_configs:
            config['x'] = min(max(config['x'], 0), self.width)
            config['y'] = min(max(config['y'], 0), self.height)
            self.add_sensor(config)
        print(f"Deployed {len(self.sensors)} sensors.")
        self._discover_all_neighbors_and_pois()

    def add_poi(self, poi_config: dict):
        """
        Dodaje pojedynczy punkt zainteresowania (POI) do sieci.

        Tworzy obiekt POI na podstawie podanej konfiguracji i dodaje go
        do wewnętrznej listy POI.

        Args:
            poi_config (dict): Słownik zawierający konfigurację pojedynczego POI
                               (musi zawierać 'id', 'x', 'y', może zawierać 'critical_level').
        """
        # Utworzenie obiektu POI
        p = POI(id=poi_config['id'], x=poi_config['x'], y=poi_config['y'],
                  critical_level=poi_config.get('critical_level', 1))
        self.pois.append(p) # Dodaj do listy POI w sieci

    def deploy_pois(self, poi_configs: list):
        """
        Rozmieszcza punkty zainteresowania (POI) w sieci na podstawie listy konfiguracji.

        Iteruje przez listę konfiguracji POI i dodaje każdy POI do sieci.
        Po rozmieszczeniu POI, aktualizuje listę monitorowanych POI dla każdego sensora.

        Args:
            poi_configs (list[dict]): Lista słowników, gdzie każdy słownik
                                      zawiera konfigurację pojedynczego POI.
        """
        for config in poi_configs:
            self.add_poi(config)
        for poi in self.pois:
            logging.info(f"POI {poi.id}: Position ({poi.pos[0]}, {poi.pos[1]}), Covered: {poi.is_covered}")
        # Po dodaniu POI, zaktualizuj listę monitorowanych POI dla każdego sensora
        for sensor in self.sensors.values():
            if not sensor.is_failed and sensor.state != SensorState.DEAD:
                sensor.monitored_pois = [p for p in self.pois if sensor.can_sense_poi(p)]

    def get_sensor(self, sensor_id):
        """
        Zwraca obiekt Sensor o podanym ID.

        Args:
            sensor_id (int): ID sensora do znalezienia.

        Returns:
            Sensor | None: Obiekt Sensor, jeśli znaleziono, w przeciwnym razie None.
        """
        return self.sensors.get(sensor_id)
    
    def broadcast_poi_coverage_info(self):
        """
        Aktywne sensory rozgłaszają informacje o tym, które POI pokrywają.

        Ta metoda jest wywoływana periodycznie (zgodnie z poi_broadcast_interval).
        Sensory w stanie ACTIVE, które nie są stacją bazową i nie są uszkodzone,
        przygotowują i wysyłają pakiet typu "POI_COVERAGE_ADVERTISEMENT"
        zawierający listę ID POI, które faktycznie pokrywają (na podstawie
        globalnego statusu pokrycia `poi.covered_by_sensors`).
        """
        # Sprawdź, czy nadszedł czas na rozgłoszenie zgodnie z interwałem
        if self.current_round % self.poi_broadcast_interval != 0:
            return

        logging.debug(f"R{self.current_round}: Broadcasting POI coverage info...")
        # Iteruj przez wszystkie sensory, aby sprawdzić, które powinny rozgłaszać
        for sensor_id, sensor_obj in self.sensors.items():
            # Tylko aktywne sensory (nie bazowe) mogą rozgłaszać
            if sensor_obj.state == SensorState.ACTIVE and not sensor_obj.is_sink and not sensor_obj.is_failed:
                # Określ, które POI ten sensor *faktycznie* pokrywa w tej rundzie
                # na podstawie GLOBALNEGO stanu pokrycia (poi.covered_by_sensors)
                currently_covering_poi_ids = set()
                for poi_obj in self.pois:
                    if sensor_id in poi_obj.covered_by_sensors: # Sprawdź, czy ten sensor jest na liście pokrywających dla POI
                        currently_covering_poi_ids.add(poi_obj.id)
                
                # Jeśli sensor pokrywa jakiekolwiek POI, przygotuj i wyślij pakiet rozgłoszeniowy
                if currently_covering_poi_ids:
                    payload = {"covered_poi_ids": list(currently_covering_poi_ids)}
                    self.communication_manager.broadcast_message(
                        sender_id=sensor_id,
                        message_type="POI_COVERAGE_ADVERTISEMENT",
                        payload=payload
                    )


    def _discover_all_neighbors_and_pois(self):
        """
        Odkrywa potencjalnych sąsiadów komunikacyjnych i monitorowane POI
        dla wszystkich żywych i nieuszkodzonych sensorów w sieci.

        Metoda ta określa fizyczne/potencjalne połączenia w sieci na podstawie
        zasięgów komunikacji i wykrywania. NIE uwzględnia aktualnego stanu
        (ACTIVE/SLEEP/DEAD) przy ustalaniu *potencjalnych* połączeń,
        ale pomija sensory martwe lub trwale uszkodzone.
        """
        # Iteruj przez wszystkie sensory, aby zaktualizować ich listy sąsiadów i monitorowanych POI
        for s_id, sensor in self.sensors.items():
            sensor.neighbors = [] # Resetuj listę sąsiadów
            sensor.monitored_pois = [] # Resetuj listę POI

            # Pomiń sensory, które są trwale uszkodzone lub martwe - one nie uczestniczą w sieci
            if sensor.is_failed or sensor.state == SensorState.DEAD:
                # print(f"DEBUG: Sensor {sensor.id} is {sensor.state}. No neighbors discovered.") # Zgodne z Twoim logiem
                continue
            
            # Odkrywanie sąsiadów (potencjalnych partnerów do komunikacji)
            for other_id, other_sensor in self.sensors.items():
                if s_id == other_id:
                    continue # Sensor nie jest swoim własnym sąsiadem
                
                # Sprawdź, czy sensory mogą się komunikować na podstawie zasięgu i statusu (nieuszkodzony/żywy)
                if sensor.can_communicate_with(other_sensor):
                    sensor.neighbors.append(other_sensor)

            # Odkrywanie POI (co sensor mógłby monitorować, gdyby był ACTIVE)
            if sensor.state != SensorState.DEAD and not sensor.is_failed : # Tylko żywe sensory mogą potencjalnie coś wykrywać
                sensor.monitored_pois = [p for p in self.pois if sensor.can_sense_poi(p)]

            # logging.debug(f"Sensor {sensor.id} ({sensor.state}) discovered {len(sensor.neighbors)} potential neighbors and {len(sensor.monitored_pois)} potentially monitorable POIs.")
            # logging.debug(f"Sensor {sensor.id} potential neighbors: {[n.id for n in sensor.neighbors]}") # Można logować ID sąsiadów dla debugowania

    def handle_sensor_failures(self):
        """"
        Obsługuje losowe awarie (śmierć) sensorów w bieżącej rundzie symulacji.

        Dla każdego sensora (z wyjątkiem bazowego i tych już uszkodzonych/martwych),
        losuje wartość. Jeśli wylosowana wartość jest mniejsza niż
        sensor_failure_prob_per_round, sensor zostaje oznaczony jako uszkodzony
        (is_failed = True) i jego stan jest zmieniany na DEAD.
        Jeśli wystąpi jakakolwiek awaria, graf sieci (sąsiedztwo) jest aktualizowany.
        """
        any_failure_occurred = False
        for sensor in self.sensors.values():
            # Sprawdź warunki: nie jest bazowym, nie jest już uszkodzony/martwy
            if not sensor.is_sink and not sensor.is_failed and sensor.state != SensorState.DEAD:
                if random.random() < self.sensor_failure_prob_per_round:
                    sensor.is_failed = True
                    sensor.state = SensorState.DEAD # Awaria traktowana jak śmierć
                    # print(f"Sensor {sensor.id} FAILED permanently at round {self.current_round}.")
                    any_failure_occurred = True
        
        if any_failure_occurred:
            # Jeśli wystąpiła awaria, odśwież graf sieci
            self._discover_all_neighbors_and_pois()

    def update_poi_coverage_objects(self, active_sensor_ids_set=None):
        """
        Aktualizuje status pokrycia dla każdego POI na podstawie aktualnego stanu
        aktywności sensorów.

        Dla każdego POI, określa, które aktualnie aktywne i nieuszkodzone
        sensory w zasięgu sensorycznym go pokrywają. Aktualizuje atrybuty
        `is_covered` (na True, jeśli >= k aktywnych sensorów pokrywa POI)
        oraz `covered_by_sensors` (zbiór ID aktywnych sensorów pokrywających POI)
        dla każdego obiektu POI.

        Args:
            active_sensor_ids_set (set[int] | None): Opcjonalny zbiór ID sensorów,
                                                    które mają być traktowane jako aktywne
                                                    dla celów tego sprawdzenia. Jeśli None,
                                                    używa aktualnych stanów sensorów w sieci.
        """
        active_ids_to_check = set()
        if active_sensor_ids_set is None: # Użyj aktualnego stanu sieci
            for s_id, s_obj in self.sensors.items():
                if s_obj.state == SensorState.ACTIVE and not s_obj.is_failed:
                    active_ids_to_check.add(s_id)
        else: # Użyj podanego zbioru
            active_ids_to_check = active_sensor_ids_set
       
        # Iteruj przez wszystkie POI w sieci
        for poi_obj in self.pois:
            current_poi_coverers_ids = set()
            for s_id in active_ids_to_check:
                sensor = self.sensors.get(s_id)
                # sprawdź, czy sensor istnieje, nie jest uszkodzony i czy potrafi sensorycznie wykryć to POI.
                if sensor and not sensor.is_failed and sensor.can_sense_poi(poi_obj):
                    current_poi_coverers_ids.add(s_id)
            poi_obj.update_coverage_status(current_poi_coverers_ids) # Aktualizuj status pokrycia obiektu POI


    def get_poi_coverage_map(self, active_sensor_ids_set: set) -> dict:
        """
        Zwraca mapę liczby aktywnych sensorów pokrywających każde POI.

        Oblicza, ile sensorów ze wskazanego zbioru `active_sensor_ids_set`
        pokrywa każde POI w sieci.

        Args:
            active_sensor_ids_set (set[int]): Zbiór ID sensorów, które mają być
                                             traktowane jako aktywne dla tego sprawdzenia.

        Returns:
            dict[int, int]: Słownik {id_poi: liczba_aktywnych_pokrywających_sensorów}.
        """
        poi_coverage_count = {poi.id: 0 for poi in self.pois}
        for poi_obj in self.pois:
            for s_id in active_sensor_ids_set:
                sensor = self.sensors.get(s_id)
                # Sprawdź, czy sensor istnieje, nie jest uszkodzony i czy potrafi sensorycznie wykryć to POI.
                if sensor and not sensor.is_failed and sensor.can_sense_poi(poi_obj):
                    poi_coverage_count[poi_obj.id] += 1
        
        return poi_coverage_count

    def _is_connected_to_sink(self, sensor_id_to_check: int, active_sensor_ids_for_path: set) -> bool:
        """
        Sprawdza, czy sensor o podanym ID może połączyć się ze stacją bazową
        za pomocą ścieżki składającej się wyłącznie z sensorów należących do zbioru
        `active_sensor_ids_for_path`.

        Wykorzystuje algorytm przeszukiwania wszerz (BFS) do znalezienia ścieżki
        od sensora do stacji bazowej, uwzględniając tylko "aktywne" sensory (te ze zbioru)
        jako możliwe węzły pośrednie w ścieżce.

        Args:
            sensor_id_to_check (int): ID sensora, dla którego sprawdzana jest łączność.
            active_sensor_ids_for_path (set[int]): Zbiór ID sensorów, które mogą być użyte
                                                 do budowy ścieżki do stacji bazowej.

        Returns:
            bool: True, jeśli istnieje ścieżka do stacji bazowej przez wskazane aktywne sensory,
                  False w przeciwnym przypadku.
        """
        if sensor_id_to_check == self.sink_id:
            return True # Stacja bazowa jest zawsze połączona sama ze sobą
        
        # Sensor musi być w zbiorze aktywnych, aby móc inicjować połączenie
        if sensor_id_to_check not in active_sensor_ids_for_path:
            return False

        # Implementacja BFS do przeszukiwania grafu sensorów
        queue = collections.deque([sensor_id_to_check])
        visited_in_bfs = {sensor_id_to_check}

        while queue:
            current_id = queue.popleft()
            current_sensor = self.sensors.get(current_id)
            if not current_sensor: continue # Na wszelki wypadek

            # Iteruj przez potencjalnych sąsiadów bieżącego sensora
            for neighbor_obj in current_sensor.neighbors: # sensor.neighbors zawiera obiekty Sensor
                if neighbor_obj.id == self.sink_id: # Dotarliśmy do stacji bazowej
                    return True
                
                # Sąsiad musi być w zbiorze aktywnych, nieuszkodzony i nieodwiedzony
                if neighbor_obj.id in active_sensor_ids_for_path and \
                   not neighbor_obj.is_failed and \
                   neighbor_obj.id not in visited_in_bfs:
                    
                    visited_in_bfs.add(neighbor_obj.id)
                    queue.append(neighbor_obj.id)
        return False # Nie znaleziono ścieżki do stacji bazowej

    def _identify_critical_targets_and_sensors(self, current_uncovered_pois: set[POI]) -> tuple[set[POI], set[Sensor]]:
        """
        Identyfikuje "krytyczne" POI i sensory, które mogłyby je pokryć
        przy najmniejszym łącznym zużyciu energii.

        Ta metoda jest częścią algorytmu CS (Cover Set). Szuka niepokrytych
        POI, które wymagają najmniejszej sumy energii od potencjalnie pokrywających
        je sensorów (nieuszkodzonych, nie-bazowych, nie-martwych), i identyfikuje
        te POI jako "krytyczne cele" oraz te sensory jako "pulę krytycznych sensorów".

        Args:
            current_uncovered_pois (set[POI]): Zbiór obiektów POI, które aktualnie
                                              nie są pokryte zgodnie z wymaganym k-pokryciem.

        Returns:
            tuple[set[POI], set[Sensor]]: Para zbiorów: krytyczne POI i krytyczne sensory.
                                          Jeśli nie ma niepokrytych POI, zwraca dwa puste zbiory.
        """
        critical_targets_set = set()
        critical_sensors_set = set()

        if not current_uncovered_pois: # Jeśli nie ma niepokrytych celów, nie ma krytycznych celów (w tym kontekście)
            for s in self.sensors.values(): s.is_critical_sensor = False
            return critical_targets_set, critical_sensors_set

        # Słowniki do przechowywania informacji o energii i sensorach pokrywających każde niepokryte POI
        # key: ID_POI, value: suma energii sensorów mogących pokryć to POI
        min_sum_energy_for_target = {poi.id: float('inf') for poi in current_uncovered_pois}
        # key: ID_POI, value: lista obiektów Sensor, które mogą pokryć to POI
        sensors_covering_each_target = {poi.id: [] for poi in current_uncovered_pois}

        # Iteruj przez wszystkie sensory, aby znaleźć te, które mogą pokryć niepokryte POI
        for sensor in self.sensors.values():
            if sensor.is_sink or sensor.is_failed or sensor.state == SensorState.DEAD:
                continue
            sensor.is_critical_sensor = False # Resetuj flagę
            # Dla każdego niepokrytego POI, sprawdź, czy bieżący sensor może je pokryć
            for poi in current_uncovered_pois:
                if sensor.can_sense_poi(poi):
                    sensors_covering_each_target[poi.id].append(sensor)
        
        # Oblicz sumę energii potencjalnie pokrywających sensorów dla każdego niepokrytego POI
        actual_sum_energy_for_target = {}
        for poi_id, covering_sensors_list in sensors_covering_each_target.items():
            if covering_sensors_list: # Jeśli są jacyś kandydaci do pokrycia
                current_sum = sum(s.current_energy for s in covering_sensors_list)
                actual_sum_energy_for_target[poi_id] = current_sum
        
        if not actual_sum_energy_for_target: # Żaden sensor nie może pokryć żadnego z niepokrytych celów
            return critical_targets_set, critical_sensors_set

        min_overall_sum_energy = min(actual_sum_energy_for_target.values())

        # Krytyczne cele to te POI, które wymagają minimalnej sumy energii do pokrycia
        for poi in current_uncovered_pois:
            if actual_sum_energy_for_target.get(poi.id) == min_overall_sum_energy:
                critical_targets_set.add(poi) # Dodaj POI do zbioru krytycznych celów
                # Krytyczne sensory to te, które mogą pokryć dowolny z krytycznych celów
                for sensor in sensors_covering_each_target[poi.id]:
                    critical_sensors_set.add(sensor)
                    sensor.is_critical_sensor = True # Oznacz sensor jako krytyczny

        return critical_targets_set, critical_sensors_set

    def _select_sensor_by_rule1(self, critical_sensors_pool: set[Sensor],
                                critical_targets_to_cover: set[POI],
                                current_cover_set_ids: set[int]) -> Sensor | None:
        """
        Wybiera pojedynczy sensor z puli krytycznych sensorów do dodania do zbioru pokrycia (CS),
        stosując regułę 1 algorytmu CS.

        Reguła 1 preferuje sensory, które:
        1. Mają wysoką preferencję działania ACTIVE (zgodnie z ich LA).
        2. Posiadają wyższy wskaźnik energii w stosunku do całkowitej energii sieci.
        3. Pokrywają nowe krytyczne cele (które nie są jeszcze pokryte przez obecny CS).
        4. (Opcjonalnie/lokalnie) Wnoszą unikalny wkład, tzn. pokrywają co najmniej jedno POI,
           które nie jest pokrywane przez ich "aktywnych" (w sensie LA) sąsiadów.

        Sortuje kandydatów według tych kryteriów i wybiera najlepszego.

        Args:
            critical_sensors_pool (set[Sensor]): Zbiór obiektów Sensor, które
                                                potencjalnie mogą pokryć krytyczne cele.
            critical_targets_to_cover (set[POI]): Zbiór obiektów POI, które są
                                                 obecnie uważane za krytyczne cele i wymagają pokrycia.
            current_cover_set_ids (set[int]): Zbiór ID sensorów, które już
                                             znajdują się w budowanym zbiorze pokrycia (CS) w tej iteracji fazy Monitoring.

        Returns:
            Sensor | None: Obiekt Sensor wybrany zgodnie z regułą 1, lub None,
                           jeśli nie znaleziono odpowiedniego kandydata.
        """
        # Jeśli pula krytycznych sensorów lub krytyczne cele są puste, nie ma kogo wybrać
        if not critical_sensors_pool or not critical_targets_to_cover:
            return None

        # Oblicz całkowitą energię wszystkich żywych, nieuszkodzonych, nie-bazowych sensorów
        total_network_energy_for_ratio = sum(s.current_energy for s_id, s in self.sensors.items()
                                           if not s.is_sink and not s.is_failed and s.state != SensorState.DEAD and s.current_energy > 0)
        if total_network_energy_for_ratio <= 1e-9: total_network_energy_for_ratio = 1.0

        candidate_sensors_data = [] # Store (sensor, prob_active, energy_ratio, num_new_crit_targets, is_locally_unique_contrib)

        # Dwa przejścia: najpierw z P(A) >= 0.5, potem (jeśli pierwszy nie znalazł) bez tego ograniczenia
        for consider_all_pa in [False, True]:
            if candidate_sensors_data and not consider_all_pa:
                # Jeśli znaleziono kandydatów w pierwszym przejściu (P(A)>=0.5), nie wykonuj drugiego
                break
            if consider_all_pa and not candidate_sensors_data:
                 logging.debug(f"R{self.current_round} _select_sensor_by_rule1: No sensor met P(A)>=0.5. Relaxing P(A) criterion.")
            
            current_pass_candidates = []
            for sensor in critical_sensors_pool:
                if sensor.id in current_cover_set_ids: continue
                if not sensor.la: continue

                prob_active = sensor.la.action_probabilities[Sensor.ACTION_ACTIVE_IDX]
                if not consider_all_pa and prob_active < 0.5:
                    continue

                energy_ratio = sensor.current_energy / total_network_energy_for_ratio if sensor.current_energy > 0 else 0.0
                
                # Określ, ile nowych krytycznych celów ten sensor pokryłby, gdyby został dodany do CS
                newly_covered_critical_pois_by_sensor = set()
                for crit_target in critical_targets_to_cover:
                    is_crit_target_already_covered_by_cs = any(
                        self.sensors[cs_member_id].can_sense_poi(crit_target) for cs_member_id in current_cover_set_ids
                    )
                    if not is_crit_target_already_covered_by_cs and sensor.can_sense_poi(crit_target):
                        newly_covered_critical_pois_by_sensor.add(crit_target)
                
                num_new_crit_targets = len(newly_covered_critical_pois_by_sensor)
                
                # Tylko sensory, które pokrywają co najmniej jeden nowy krytyczny cel, są kandydatami
                if num_new_crit_targets > 0:
                    # Sprawdź, czy sensor wnosi unikalny wkład lokalnie, tzn. czy pokrywa
                    # co najmniej jeden nowy krytyczny cel, który NIE JEST pokrywany przez
                    # jego "aktywnych" sąsiadów (tych, którzy mają P(A) >= 0.5)

                    is_locally_unique_contribution = False 
                    
                    if not newly_covered_critical_pois_by_sensor:
                        is_locally_unique_contribution = False
                    else:
                        for poi_it_newly_covers in newly_covered_critical_pois_by_sensor:
                            is_this_poi_covered_by_active_neighbors = False
                            # Iteruj przez sąsiadów i ich pokrycie POI z poprzedniej rundy
                            for neighbor_id, neighbor_covered_pois_set in sensor.neighbor_poi_coverage.items():
                                # Sprawdź, czy sąsiad istnieje i ma LA oraz czy jego P(A) >= 0.5 (jego "chęć" bycia aktywnym)
                                neighbor_obj = self.sensors.get(neighbor_id)
                                if neighbor_obj and neighbor_obj.la and \
                                   neighbor_obj.la.action_probabilities[Sensor.ACTION_ACTIVE_IDX] >= 0.5: # Neighbor is "willing" to be active
                                    if poi_it_newly_covers.id in neighbor_covered_pois_set:
                                        is_this_poi_covered_by_active_neighbors = True
                                        break 
                            # Jeśli żaden z "aktywnych" sąsiadów nie pokrywa tego POI, sensor wnosi unikalny wkład        
                            if not is_this_poi_covered_by_active_neighbors:
                                is_locally_unique_contribution = True # Found at least one POI it uniquely covers locally
                                break
                    
                    current_pass_candidates.append(
                        (sensor, prob_active, energy_ratio, num_new_crit_targets, is_locally_unique_contribution)
                    )
            
            if current_pass_candidates: # Jeśli znaleziono kandydatów w bieżącym przejściu, użyj ich
                candidate_sensors_data = current_pass_candidates
                if not consider_all_pa: # Jeśli to było pierwsze przejście (z ograniczeniem P(A)), przerwij
                    break

        if not candidate_sensors_data:
            logging.debug(f"R{self.current_round} _select_sensor_by_rule1: No candidates found even after relaxing P(A).")
            return None

        logging.debug(f"R{self.current_round} _select_sensor_by_rule1: Candidates before sort ({len(candidate_sensors_data)}):")
        for cand_data_log in candidate_sensors_data:
            s_obj, pa, er, nuctc, local_u = cand_data_log
            logging.debug(f"  Sensor {s_obj.id}: num_new_crit={nuctc}, P(A)={pa:.3f}, E_ratio={er:.3f}, LocallyUnique={local_u}")

        # Sortowanie kandydatów zgodnie z regułą 1 (od najlepszego do najgorszego)
        # Kryteria sortowania:
        # 1. num_new_crit_targets (malejąco - im więcej nowych krytycznych celów pokrywa, tym lepiej)
        # 2. is_locally_unique_contribution (malejąco - True jest lepsze niż False)
        # 3. prob_active (malejąco - wyższe P(A) jest lepsze)
        # 4. energy_ratio (malejąco - wyższy wskaźnik energii jest lepszy)
        candidate_sensors_data.sort(key=lambda x: (x[3], x[4], x[1], x[2]), reverse=True)
        
        selected_sensor_tuple = candidate_sensors_data[0]
        selected_sensor = selected_sensor_tuple[0]
        logging.debug(f"R{self.current_round} _select_sensor_by_rule1: Selected {selected_sensor.id} (NewCrit:{selected_sensor_tuple[3]}, LocalU:{selected_sensor_tuple[4]}, P(A):{selected_sensor_tuple[1]:.3f})")
        return selected_sensor

    def _trim_cover_set(self, current_cover_set_ids: set[int], all_pois_list: list[POI]) -> set[int]:
        """
        Minimalizuje zbiór pokrycia (CS) poprzez usuwanie powtarzających się sensorów.

        Iteruje przez sensory w podanym zbiorze CS i sprawdza, czy usunięcie
        danego sensora spowodowałoby utratę pokrycia wymaganych POI. Jeśli
        usunięcie sensora nie narusza pokrycia (wszystkie POI są nadal pokryte
        przez co najmniej k aktywnych sensorów pozostałych w zbiorze), sensor
        jest usuwany z CS jako powtarzający się. Proces ten jest iteracyjny.

        Args:
            current_cover_set_ids (set[int]): Zbiór ID sensorów, które zostały
                                             wybrane do początkowego zbioru pokrycia (CS).
            all_pois_list (list[POI]): Lista wszystkich obiektów POI w sieci.

        Returns:
            set[int]: Zbiór ID sensorów reprezentujący zminimalizowany (przycięty) CS.
        """
        trimmed_cs_ids = current_cover_set_ids.copy()
        
        # Przygotuj listę sensorów w CS do sprawdzenia redundancji.
        sensors_to_check_for_redundancy = sorted(
            [self.sensors[s_id] for s_id in trimmed_cs_ids],
            key=lambda s: s.current_energy # Spróbuj usunąć te z najniższą energią najpierw
        )

        for sensor_to_remove in sensors_to_check_for_redundancy:
            if sensor_to_remove.id not in trimmed_cs_ids: # Już usunięty w tej iteracji Trim
                continue

            # Tymczasowo usuń sensor z CS
            temp_cs_after_removal = trimmed_cs_ids - {sensor_to_remove.id}
            
            # Sprawdź, czy wszystkie POI są nadal pokryte przez temp_cs_after_removal
            all_pois_still_covered = True
            current_poi_coverage_map = self.get_poi_coverage_map(temp_cs_after_removal)
            for poi in all_pois_list:
                if current_poi_coverage_map.get(poi.id, 0) < 1: # Zakładamy k=1 (pełne pokrycie)
                    all_pois_still_covered = False
                    break
            
            if all_pois_still_covered:
                # Usunięcie tego sensora nie naruszyło pokrycia, więc się powtarza
                trimmed_cs_ids.remove(sensor_to_remove.id)
                # print(f"Trim: Sensor {sensor_to_remove.id} removed as redundant.")
            # else: sensor jest potrzebny, zostaw go w CS
            
        return trimmed_cs_ids

    def network_setup_phase(self):
        """
        FAZA 1: Network Setup. Wykonywana tylko raz podczas pierwszej rundy symulacji.

        Inicjalizuje automaty uczące (LA) wszystkich sensorów, ustawiając ich
        prawdopodobieństwa wyboru akcji (np. P(ACTIVE)=P(SLEEP)=0.5).
        Wykonuje wstępne odkrycie sąsiadów i monitorowanych POI.
        Inicjalizuje progi Th i Eth używane w mechanizmie nagradzania LA.
        Ustawia flagę `is_first_iteration` na False.
        """
        if self.is_first_iteration:
            # Krok 1.1: Inicjalizacja Automatów Uczących sensorów
            for sensor in self.sensors.values():
                if sensor.la:
                    sensor.la.initialize_probabilities() # Ustawia P(ACTIVE)=P(SLEEP)=0.5

            # Krok 1.2: Wstępne odkrycie grafu sieci (sąsiedztwo i zasięg POI)
            self._discover_all_neighbors_and_pois()
            
            # Krok 1.3: Inicjalizacja progów nagradzania (Th i Eth)
            # Te progi są używane do oceny "jakości" zbioru pokrycia (CS)
            # i nagradzania sensorów, które do niego należą.
            # Początkowe wartości powinny być takie, aby pierwszy "sensowny" CS
            # został nagrodzony.
            self.min_Th_cardinality_observed = float('inf')
            self.max_Eth_remaining_energy_observed = 0.0 # Lub -float('inf')

            self.is_first_iteration = False

    def learning_phase(self):
        """
        FAZA 2: Learning. Wykonywana na początku każdej rundy symulacji.

        W tej fazie, każdy sensor posiadający automat uczący (LA) aktualizuje
        prawdopodobieństwa wyboru swoich akcji (ACTIVE/SLEEP) na podstawie
        swojego aktualnego poziomu energii w stosunku do całkowitej energii
        pozostałej w sieci. Sensory z większą ilością energii stają się bardziej
        skłonne do wyboru akcji ACTIVE.
        """
        # Krok 2.1: Obliczenie całkowitej energii żywych, nieuszkodzonych sensorów (bez sinka)
        total_network_energy = sum(s.current_energy for s in self.sensors.values()
                                   if not s.is_sink and not s.is_failed and s.state != SensorState.DEAD and s.current_energy > 0)
        
        # Jeśli całkowita energia sieci jest zero lub bliska zeru, wszystkie sensory powinny preferować SLEEP
        if total_network_energy <= 1e-9:
            for sensor in self.sensors.values():
                if sensor.la: # Dotyczy tylko sensorów z LA
                    sensor.la.set_probabilities_based_on_energy_ratio(0.0)
            return
        
        # Krok 2.2: Aktualizacja prawdopodobieństw LA na podstawie wskaźnika energii
        for sensor in self.sensors.values():
            if sensor.la:
                # Oblicz wskaźnik energii dla sensora
                energy_ratio = sensor.current_energy / total_network_energy if sensor.current_energy > 0 else 0.0
                sensor.la.set_probabilities_based_on_energy_ratio(energy_ratio)

    def monitoring_phase(self) -> tuple[set[int] | None, float | None]:
        """
        FAZA 3: Monitoring. Wykonywana w każdej rundzie po fazie Learning.

        Implementuje algorytm tworzenia zbioru pokrycia (CS) i wyboru sensorów mostów.
        Proces jest iteracyjny i polega na:
        1. Identyfikacji niepokrytych POI (krytycznych celów).
        2. Wyborze sensora z puli krytycznych sensorów (wg Reguły 1) do dodania do CS.
        3. Powtarzaniu kroków 1-2 aż wszystkie POI będą pokryte lub nie będzie
           można dodać więcej sensorów do CS.
        4. Przycięciu (minimalizacji) początkowego CS.
        5. Identyfikacji i aktywacji sensorów mostów w celu zapewnienia łączności
           sensorów z CS ze stacją bazową.
        6. Obliczeniu czasu pracy (W) dla finalnego zbioru operacyjnego.
        7. Określeniu, czy finalny CS zasługuje na nagrodę dla automatów uczących,
           na podstawie wybranej metody nagradzania ("cardinality" lub "energy")
           i zaktualizowaniu prawdopodobieństw LA sensorów w CS.

        Jeśli nie uda się utworzyć CS (np. brak sensorów, brak łączności),
        ustawia flagę `coverage_lost` na True.

        Returns:
            tuple[set[int] | None, float | None]: Para:
                                                  - Zbiór ID sensorów należących do finalnego,
                                                    operacyjnego zbioru pokrycia (CS) i mostów,
                                                    lub None jeśli CS nie mógł być utworzony.
                                                  - Czas pracy (W) dla tego zbioru, lub None.
        """
        logging.debug(f"R{self.current_round} - Monitoring Phase Start")
        current_cover_set_ids_for_coverage = set()
        uncovered_pois = set(self.pois)

        # Krok 3.1: Tworzenie początkowego zbioru pokrycia (CS)
        # Iteracyjny proces dodawania sensorów do CS, dopóki wszystkie POI nie będą pokryte
        # lub nie będzie można dodać więcej sensorów spełniających kryteria.
        max_cs_formation_iterations = len(self.sensors) + len(self.pois)
        for iter_num in range(max_cs_formation_iterations):
            if not uncovered_pois:
                logging.debug(f"  All POIs covered after {iter_num} CS formation iterations.")
                break
            
            logging.debug(f"  CS Formation Iter: {iter_num+1}, Uncovered POIs: {[p.id for p in uncovered_pois]}")
            critical_targets, critical_sensors_pool = self._identify_critical_targets_and_sensors(uncovered_pois)
            
            if not critical_targets:
                logging.debug(f"  No more critical targets. Uncovered: {[p.id for p in uncovered_pois]}. Attempting fallback.")
                best_fallback_sensor = None
                
                potential_fallback_candidates_data = []
                for s_obj in self.sensors.values():
                    if s_obj.id not in current_cover_set_ids_for_coverage and \
                       not s_obj.is_failed and s_obj.state != SensorState.DEAD and s_obj.la:
                        
                        newly_covered_by_s_obj = {p for p in uncovered_pois if s_obj.can_sense_poi(p)}
                        num_newly_covered = len(newly_covered_by_s_obj)

                        if num_newly_covered > 0:
                            prob_active = s_obj.la.action_probabilities[Sensor.ACTION_ACTIVE_IDX]
                            energy_val = s_obj.current_energy
                            
                            is_locally_unique_fallback = False
                            for poi_it_newly_covers in newly_covered_by_s_obj:
                                is_this_poi_covered_by_active_neighbors = False
                                for neighbor_id, neighbor_covered_pois_set in s_obj.neighbor_poi_coverage.items():
                                    neighbor_obj_fallback = self.sensors.get(neighbor_id)
                                    if neighbor_obj_fallback and neighbor_obj_fallback.la and \
                                       neighbor_obj_fallback.la.action_probabilities[Sensor.ACTION_ACTIVE_IDX] >= 0.5:
                                        if poi_it_newly_covers.id in neighbor_covered_pois_set:
                                            is_this_poi_covered_by_active_neighbors = True
                                            break
                                if not is_this_poi_covered_by_active_neighbors:
                                    is_locally_unique_fallback = True
                                    break
                            potential_fallback_candidates_data.append(
                                (s_obj, num_newly_covered, is_locally_unique_fallback, prob_active, energy_val)
                            )
                
                # Jeśli znaleziono kandydatów awaryjnych
                if potential_fallback_candidates_data:
                    # Sortuj kandydatów awaryjnych: najwięcej nowych POI (DESC), unikalny wkład (DESC), P(A) (DESC), energia (DESC)
                    potential_fallback_candidates_data.sort(key=lambda x: (x[1], x[2], x[3], x[4]), reverse=True)
                    best_fallback_sensor = potential_fallback_candidates_data[0][0]
                                
                # Jeśli wybrano sensor awaryjny
                if best_fallback_sensor:
                    current_cover_set_ids_for_coverage.add(best_fallback_sensor.id)
                    newly_covered_by_selected_fallback = {p for p in uncovered_pois if best_fallback_sensor.can_sense_poi(p)}
                    uncovered_pois -= newly_covered_by_selected_fallback
                    logging.debug(f"  Fallback selected Sensor {best_fallback_sensor.id}. Covered {len(newly_covered_by_selected_fallback)} new POIs. Uncovered: {[p.id for p in uncovered_pois]}")
                    continue
                else:
                    logging.debug(f"  Fallback could not select a sensor. Uncovered: {[p.id for p in uncovered_pois]}")
                    break 
                
            if not critical_sensors_pool:
                logging.debug(f"  No critical sensors available. Uncovered: {[p.id for p in uncovered_pois]}")
                break

            # Krok 3.2: Wybierz sensor zgodnie z Regułą 1 z puli krytycznych sensorów
            sensor_selected_by_rule1 = self._select_sensor_by_rule1(
                critical_sensors_pool, critical_targets, current_cover_set_ids_for_coverage
            )
            if sensor_selected_by_rule1:
                current_cover_set_ids_for_coverage.add(sensor_selected_by_rule1.id)
                newly_covered_by_selected_rule1 = {p for p in uncovered_pois if sensor_selected_by_rule1.can_sense_poi(p)}
                uncovered_pois -= newly_covered_by_selected_rule1
                logging.debug(f"  Rule 1 selected Sensor {sensor_selected_by_rule1.id}. Covered {len(newly_covered_by_selected_rule1)} new POIs. Uncovered POIs: {[p.id for p in uncovered_pois]}")
            else:
                logging.debug(f"  Rule 1 did not select any sensor. Uncovered POIs: {[p.id for p in uncovered_pois]}")
                break
        
        # Krok 3.3: Sprawdzenie, czy udało się utworzyć CS (czy są jacyś kandydaci)
        if uncovered_pois and not current_cover_set_ids_for_coverage and self.pois:
            logging.warning(f"R{self.current_round}: Monitoring Phase - Could not form any initial coverage set. {len(uncovered_pois)} POIs remain.")
            self.coverage_lost = True
            return None, None

        # Krok 3.4: Przycięcie (minimalizacja) zbioru pokrycia (CS)
        trimmed_cs_ids_for_coverage = self._trim_cover_set(current_cover_set_ids_for_coverage, self.pois)
        logging.debug(f"R{self.current_round}: CS for coverage after Trim: {trimmed_cs_ids_for_coverage} (Size: {len(trimmed_cs_ids_for_coverage)})")

        # Sprawdzenie po przycięciu - czy CS nadal istnieje i czy pokrywa wszystkie POI
        if not trimmed_cs_ids_for_coverage and self.pois:
            logging.warning(f"R{self.current_round}: Monitoring Phase - Trimmed CS for coverage is empty, but POIs exist.")
            self.coverage_lost = True
            return None, None
        # Krok 3.5: Zapewnienie łączności CS ze stacją bazową
        final_active_set = trimmed_cs_ids_for_coverage.copy()
        if self.sink_node and not self.sink_node.is_failed: 
            final_active_set.add(self.sink_id)

        bridge_sensors_activated_in_this_phase = set()
        max_outer_connectivity_loops = len(self.sensors) 
        for k_loop in range(max_outer_connectivity_loops):
            disconnected_covering_sensors = set()
            for s_id_cov in trimmed_cs_ids_for_coverage:
                if not self._is_connected_to_sink(s_id_cov, final_active_set):
                    disconnected_covering_sensors.add(s_id_cov)
            if not disconnected_covering_sensors:
                logging.debug(f"R{self.current_round}: Connectivity Loop {k_loop+1}: All covering sensors are connected.")
                break
            
            logging.info(f"R{self.current_round}: Connectivity Loop {k_loop+1}: {len(disconnected_covering_sensors)} covering sensors disconnected: {disconnected_covering_sensors}. Current active set for pathfinding: {final_active_set}")
            activated_at_least_one_bridge_in_iteration = False
            
            # Sortuj odłączone sensory
            sorted_disconnected_sensors = sorted(list(disconnected_covering_sensors))

            # Dla każdego odłączonego sensora w CS, spróbuj znaleźć najlepszy sensor mostu
            for sensor_to_connect_id in sorted_disconnected_sensors:
                if self._is_connected_to_sink(sensor_to_connect_id, final_active_set):
                    continue
                best_bridge_candidate_id = None
                highest_utility_for_bridge = -float('inf')
                # Wagi
                W_BRIDGE_ENERGY = 0.6 
                W_BRIDGE_LA_PREF = 0.4 

                # Iteruj przez WSZYSTKIE żywe, nieuszkodzone sensory (z wyjątkiem tych już w `final_active_set_for_pathfinding`)
                # aby znaleźć najlepszego kandydata na most.
                for s_id_candidate, sensor_candidate_obj in self.sensors.items():
                    if s_id_candidate in final_active_set or \
                       sensor_candidate_obj.is_failed or \
                       sensor_candidate_obj.state == SensorState.DEAD:
                        continue

                    hypothetical_active_set_with_bridge = final_active_set | {s_id_candidate}
                    # Sprawdź, czy dodanie kandydata na most połączyłoby `sensor_to_connect_id` z stacją bazową
                    if self._is_connected_to_sink(sensor_to_connect_id, hypothetical_active_set_with_bridge):
                        energy_component = sensor_candidate_obj.current_energy / sensor_candidate_obj.initial_energy if sensor_candidate_obj.initial_energy > 0 else 0
                        la_preference_component = 0.0
                        if sensor_candidate_obj.la:
                            la_preference_component = sensor_candidate_obj.la.action_probabilities[Sensor.ACTION_ACTIVE_IDX]
                        
                        utility = (W_BRIDGE_ENERGY * energy_component) + \
                                  (W_BRIDGE_LA_PREF * la_preference_component)
                                  
                        if utility > highest_utility_for_bridge:
                            highest_utility_for_bridge = utility
                            best_bridge_candidate_id = s_id_candidate
                
                if best_bridge_candidate_id:
                    logging.info(f"R{self.current_round}: Connectivity - Activating bridge Sensor {best_bridge_candidate_id} (E:{self.sensors[best_bridge_candidate_id].current_energy:.2f}, Util:{highest_utility_for_bridge:.2f}) to connect {sensor_to_connect_id}.")
                    final_active_set.add(best_bridge_candidate_id)
                    bridge_sensors_activated_in_this_phase.add(best_bridge_candidate_id)
                    activated_at_least_one_bridge_in_iteration = True
                    break
            
            if not activated_at_least_one_bridge_in_iteration and k_loop >= 0 : # jeśli k_loop=0 i nic nie aktywowano, to też przerwij
                logging.warning(f"R{self.current_round}: Connectivity Loop {k_loop+1}: No further bridges could be activated. Disconnected sensors may remain.")
                break
        
        if self.pois:
            for s_id_cov in trimmed_cs_ids_for_coverage:
                if not self._is_connected_to_sink(s_id_cov, final_active_set):
                    logging.error(f"R{self.current_round}: MONITORING CRITICAL - Sensor {s_id_cov} (from coverage set) still DISCONNECTED (final active set for path check: {final_active_set}). Coverage lost.")
                    self.coverage_lost = True
                    return None, None
        
        # Krok 3.6: Ustalenie finalnego operacyjnego zbioru sensorów (CS + Mosty)
        final_cs_ids_for_operation = (trimmed_cs_ids_for_coverage | bridge_sensors_activated_in_this_phase)
        if self.sink_id is not None:
            final_cs_ids_for_operation.discard(self.sink_id)

        # Krok 3.7: Obliczenie czasu pracy (W) dla finalnego zbioru operacyjnego
        if not final_cs_ids_for_operation and self.pois:
            logging.warning(f"R{self.current_round}: Monitoring Phase - Final operational cover set is empty, but POIs exist.")
            self.coverage_lost = True
            return None, None

        working_time_W = 0.0
        if final_cs_ids_for_operation:
            energies_in_cs = [self.sensors[s_id].current_energy for s_id in final_cs_ids_for_operation if s_id in self.sensors and self.sensors[s_id].current_energy > 1e-9]
            min_energy_in_final_cs = min(energies_in_cs) if energies_in_cs else 0.0
            
            defined_working_time_slice = 0.5
            if self.config and self.config.has_option("NetworkLogic", "cover_set_working_time_slice"):
                 defined_working_time_slice = self.config.getfloat("NetworkLogic", "cover_set_working_time_slice")
            else:
                 logging.warning("Config for 'cover_set_working_time_slice' not found, using default 0.5")

            working_time_W = min(defined_working_time_slice, min_energy_in_final_cs)
            if working_time_W < 1e-9 : working_time_W = 0.0
            logging.debug(f"R{self.current_round}: Working time W for final CS (size {len(final_cs_ids_for_operation)}): {working_time_W:.3f}")
        
        # Krok 3.8: Nagradzanie sensorów w finalnym CS za pomocą LA
        is_reward_for_this_cs = False
        if final_cs_ids_for_operation:
            if self.reward_method == "cardinality":
                # Metoda "cardinality": nagradzaj, jeśli rozmiar CS jest mniejszy lub równy najlepszemu zaobserwowanemu
                cs_cardinality = len(final_cs_ids_for_operation)
                assert isinstance(cs_cardinality, int)
                assert isinstance(self.min_Th_cardinality_observed, (int, float))
                if cs_cardinality <= self.min_Th_cardinality_observed:
                    is_reward_for_this_cs = True
                    if cs_cardinality < self.min_Th_cardinality_observed:
                        self.min_Th_cardinality_observed = cs_cardinality
                        logging.info(f"R{self.current_round}: New best CS cardinality: {self.min_Th_cardinality_observed}")
            elif self.reward_method == "energy":
                # Metoda "energy": nagradzaj, jeśli sumaryczna pozostała energia sensorów w CS
                # jest większa lub równa najlepszej zaobserwowanej sumie energii.
                cs_total_remaining_energy = sum(self.sensors[s_id].current_energy for s_id in final_cs_ids_for_operation if s_id in self.sensors)
                assert isinstance(cs_total_remaining_energy, (int, float))
                assert isinstance(self.max_Eth_remaining_energy_observed, (int, float))
                if cs_total_remaining_energy >= self.max_Eth_remaining_energy_observed:
                    is_reward_for_this_cs = True
                    if cs_total_remaining_energy > self.max_Eth_remaining_energy_observed:
                        self.max_Eth_remaining_energy_observed = cs_total_remaining_energy
                        logging.info(f"R{self.current_round}: New best CS total remaining energy: {self.max_Eth_remaining_energy_observed:.2f}")
            
            # Zastosowanie nagrody do automatów uczących sensorów w finalnym CS
            logging.debug(f"R{self.current_round}: Decision for CS (reward={is_reward_for_this_cs}) applied to LAs of {len(final_cs_ids_for_operation)} sensors.")
            for s_id in final_cs_ids_for_operation:
                sensor = self.sensors.get(s_id) # Użyj .get() dla bezpieczeństwa
                if sensor and sensor.la:
                    actual_reward_signal_for_sensor = is_reward_for_this_cs 
                    
                    if is_reward_for_this_cs: # Tylko jeśli globalnie CS jest OK
                        is_locally_redundant_within_cs = True # Załóż redundancję
                        
                        pois_covered_by_s_id_in_cs = {
                            p.id for p in self.pois 
                            if s_id in p.covered_by_sensors
                        }

                        if not pois_covered_by_s_id_in_cs: # Jeśli nie pokrywa nic (np. jest tylko mostem)
                            is_locally_redundant_within_cs = False
                        else:
                            for poi_id_covered_by_s in pois_covered_by_s_id_in_cs:
                                # Czy jakiś inny sąsiad s_id, który też jest w final_cs_ids_for_operation, pokrywa ten POI?
                                is_poi_also_covered_by_active_cs_neighbor = False
                                for neighbor_obj_id_in_cs in sensor.neighbor_poi_coverage: # Klucze to ID sąsiadów
                                    if neighbor_obj_id_in_cs in final_cs_ids_for_operation and neighbor_obj_id_in_cs != s_id:
                                        if poi_id_covered_by_s in sensor.neighbor_poi_coverage.get(neighbor_obj_id_in_cs, set()):
                                            is_poi_also_covered_by_active_cs_neighbor = True
                                            break
                                if not is_poi_also_covered_by_active_cs_neighbor:
                                    is_locally_redundant_within_cs = False # Znalazł POI, które pokrywa "unikalnie" lokalnie w CS
                                    break
                        
                        if is_locally_redundant_within_cs:
                            logging.debug(f"  Sensor {s_id} in good CS is locally redundant w.r.t other CS members. No reward for its LA.")
                            actual_reward_signal_for_sensor = False # Nie nagradzaj, jeśli redundantny lokalnie
                    
                    sensor.la.update_probabilities_LRI(Sensor.ACTION_ACTIVE_IDX, actual_reward_signal_for_sensor)
        
        return final_cs_ids_for_operation, working_time_W
    
    def update_phase(self, cover_set_to_update_ids: set[int] | None, energy_reduction_W: float | None):
        """
        FAZA 4: Update. Wykonywana w każdej rundzie po fazie Monitoring.

        W tej fazie aktualizowane są stany sensorów oraz ich poziomy energii
        na podstawie wyniku fazy Monitoring.
        1. Sensory należące do finalnego operacyjnego zbioru (CS + Mosty)
           zużywają energię proporcjonalnie do czasu pracy W i ustawiają stan na ACTIVE.
        2. Pozostałe sensory ustawiają stan na SLEEP i zużywają minimalną energię uśpienia.
        3. Sensory, których energia spadła do zera lub które uległy awarii,
           zmieniają stan na DEAD.
        4. Stacja bazowa (sink) zawsze pozostaje w stanie ACTIVE (jeśli nie uległa awarii).

        Args:
            cover_set_to_update_ids (set[int] | None): Zbiór ID sensorów, które należą
                                                     do finalnego operacyjnego zbioru
                                                     (CS i mosty) i będą aktywne. None,
                                                     jeśli nie udało się utworzyć CS.
            energy_reduction_W (float | None): Czas pracy (W) obliczony w fazie Monitoring.
                                              None, jeśli nie udało się utworzyć CS.
        """
        # Krok 4.1: Redukcja energii sensorów w CS
        if cover_set_to_update_ids and energy_reduction_W is not None and energy_reduction_W > 1e-9: # Tylko jeśli W > 0
            for s_id in cover_set_to_update_ids:
                sensor = self.sensors[s_id]
                sensor.update_energy(amount=energy_reduction_W) # Metoda update_energy w Sensorze obsłuży odejmowanie energii i przejście do stanu DEAD, jeśli energia spadnie do 0.

        # Krok 4.2: Ustawienie ostatecznych stanów sensorów
        for s_id, sensor_obj in self.sensors.items():
            if sensor_obj.is_sink:
                sensor_obj.state = SensorState.ACTIVE # Sensor bazowy zawsze aktywny
                continue
            
            # Jeśli sensor umarł (np. przez awarię lub zużycie energii), jego stan to DEAD
            if sensor_obj.is_failed or sensor_obj.current_energy <= 1e-9:
                sensor_obj.state = SensorState.DEAD
                continue

            # Jeśli CS istnieje i sensor jest jego częścią -> ACTIVE
            if cover_set_to_update_ids and s_id in cover_set_to_update_ids:
                sensor_obj.state = SensorState.ACTIVE
            else: # W przeciwnym razie -> SLEEP
                sensor_obj.state = SensorState.SLEEP
                # Koszt bycia w stanie SLEEP (bardzo mały)
                sensor_obj.update_energy(activity_type=SensorState.SLEEP, duration=1.0) # Zakładamy, że runda to 1 jednostka czasu

    def run_one_round(self):
        """
        Wykonuje jedną pełną rundę symulacji.

        Przebieg rundy obejmuje następujące fazy:
        1. **Network Setup (tylko w pierwszej rundzie):** Inicjalizacja LA i wstępne odkrycie sieci.
        2. **Sensor Failures:** Losowe awarie sensorów.
        3. **Learning:** Sensory aktualizują P(ACTIVE) na podstawie wskaźnika energii i przetwarzają komunikaty od sąsiadów.
        4. **Monitoring:** Algorytm tworzenia i optymalizacji zbioru pokrycia (CS) i sensorów mostów. Określenie czasu pracy W i sygnału nagrody dla LA.
        5. **Update:** Aktualizacja stanów sensorów (ACTIVE/SLEEP/DEAD) i zużycie energii na podstawie wyniku fazy Monitoring.
        6. **POI Coverage Update:** Globalna aktualizacja statusu pokrycia każdego POI na podstawie sensorów, które są aktywne po fazie Update.
        7. **POI Coverage Broadcast:** Aktywne sensory rozgłaszają informacje o pokryciu POI (co X rund).
        8. **Report Generation:** Generowanie pakietów danych (np. raportów o pokryciu POI) przez aktywne sensory, jeśli spełnione są kryteria.
        9. **Data Routing:** Próba przesłania pakietów danych ze skrzynek odbiorczych sensorów do sinka przy użyciu protokołu routingu (np. Dijkstra z uwzględnieniem energii).
        10. **Statistics Collection:** Zbieranie statystyk dotyczących stanu sieci w tej rundzie (energia, stany, pokrycie, PDR, opóźnienie).

        Args:
             None.

        Returns:
            dict | None: Słownik zawierający statystyki rundy, lub None w przypadku krytycznego błędu.
        """
        self.current_round += 1
        logging.info(f"--- Starting Round {self.current_round} ---")

        # Krok 1: Faza Network Setup (tylko w pierwszej rundzie)
        if self.is_first_iteration:
            self.network_setup_phase()

        # Krok 2: Obsługa awarii sensorów
        self.handle_sensor_failures()

        # Krok 3: Faza Learning
        self.learning_phase()

        # Krok 4: Faza Monitoring - tworzenie CS, mosty, W, nagroda LA
        final_cs_ids, working_time = self.monitoring_phase() # Ta faza ustala, które sensory są w CS
        
        # Krok 5: Faza Update - aktualizacja stanów sensorów i zużycie energii
        self.update_phase(final_cs_ids, working_time)

        # Krok 6: Globalna aktualizacja statusu pokrycia POI
        active_sensors_after_update = {
            s.id for s in self.sensors.values() if s.state == SensorState.ACTIVE and not s.is_failed
        }
        self.update_poi_coverage_objects(active_sensor_ids_set=active_sensors_after_update)

        # Krok 7: Rozgłaszanie informacji o pokryciu POI (co X rund)
        self.broadcast_poi_coverage_info()

        if self.coverage_lost:
            logging.warning(f"R{self.current_round}: Coverage lost flag is True. Further rounds might be unproductive.")
        
        if final_cs_ids is not None and self.pois:
            # Krok 8: Generowanie raportów POI
            self.generate_poi_reports()
            # Krok 9: Routing danych do stacji bazowej
            self.route_data_to_sink()
        elif not self.pois:
            logging.debug(f"R{self.current_round}: No POIs to cover. Skipping report generation and routing.")
        else:
            logging.warning(f"R{self.current_round}: No cover set formed. Skipping report generation and routing.")
        
        # Krok 10: Zbieranie statystyk rundy
        stats = self.collect_round_statistics()
        logging.info(f"--- Finished Round {self.current_round} --- ActiveS:{stats['active_sensors']}, Qk:{stats['coverage_q_k']:.2f}, PDR:{stats.get('pdr',0.0):.2f}")
        return stats

    def generate_poi_reports(self):
        """
        Generuje raporty o pokryciu POI przez aktywne sensory.

        Sensory w stanie ACTIVE, które nie są sinkiem i nie są uszkodzone,
        sprawdzają, czy POI w ich zasięgu sensorycznym spełniają wymóg k-pokrycia
        (na podstawie globalnego statusu pokrycia POI). Jeśli tak, sensor generuje
        pakiet raportu o tym POI i dodaje go do swojego bufora danych do wysłania.
        """
        active_sensor_ids_for_reporting = {
            s.id for s in self.sensors.values() 
            if s.state == SensorState.ACTIVE and not s.is_failed
        }

        current_poi_coverage_map = self.get_poi_coverage_map(active_sensor_ids_for_reporting)

        # Iteruj przez sensory, które mogą generować raporty
        for sensor_obj in self.sensors.values():
            if sensor_obj.state == SensorState.ACTIVE and not sensor_obj.is_failed and not sensor_obj.is_sink:
                for poi_obj in sensor_obj.monitored_pois:
                    if sensor_obj.can_sense_poi(poi_obj) and \
                       current_poi_coverage_map.get(poi_obj.id, 0) >= self.k_coverage_level:

                        # Utwórz nowy pakiet danych
                        payload = {
                            "poi_id": poi_obj.id, 
                            "status": f"k-covered (count: {current_poi_coverage_map.get(poi_obj.id, 0)})", 
                            "reporter_id": sensor_obj.id
                        }
                        packet = Packet(source_id=sensor_obj.id,
                                        destination_id=self.sink_id,
                                        data_type="POI_REPORT_K_COVERAGE",
                                        payload=payload)
                        packet.creation_time = self.current_round
                        sensor_obj.data_buffer.append(packet)
                        self.total_packets_generated += 1
                        logging.debug(f"Packet generated. Total packets generated: {self.total_packets_generated}")
                        break

    def route_data_to_sink(self):
        """
        Próbuje przesłać pakiety danych ze skrzynek odbiorczych aktywnych sensorów
        do stacji bazowej (sink).

        Wykorzystuje funkcję routingu (`find_shortest_path_to_sink_dijkstra_energy_aware`)
        do znalezienia ścieżki do sinka przez aktywne sensory. Jeśli ścieżka istnieje,
        sensor próbuje wysłać pakiet do pierwszego sąsiada na ścieżce.
        CommunicationManager obsługuje rzeczywistą transmisję i potencjalną utratę pakietu.
        Pakiety dostarczone do sinka są zliczane, a ich opóźnienie sumowane.
        """
        from .routing import find_shortest_path_to_sink_dijkstra_energy_aware 

        active_sensor_ids_for_routing = {
            s.id for s in self.sensors.values()
            if s.state == SensorState.ACTIVE and not s.is_failed
        }
        if self.sink_node and self.sink_node.state == SensorState.ACTIVE and not self.sink_node.is_failed:
             active_sensor_ids_for_routing.add(self.sink_id)
        
        if not active_sensor_ids_for_routing:
            logging.warning(f"R{self.current_round} route_data_to_sink: No sensors in active_sensor_ids_for_routing. Skipping routing.")
            return

        # Iteruj przez wszystkie sensory, które mogą mieć pakiety do wysłania (czyli są aktywne i nie są stacją bazową) 
        for s_id, sensor_obj in self.sensors.items():
            if sensor_obj.is_sink or sensor_obj.state != SensorState.ACTIVE or \
               sensor_obj.is_failed or not sensor_obj.data_buffer:
                continue

            packets_to_remove_from_buffer = []
            for packet_idx, packet in enumerate(list(sensor_obj.data_buffer)):
                if packet.destination_id != self.sink_id:
                    logging.debug(f"R{self.current_round} Packet {packet.id} (src:{packet.source_id}) in sensor {s_id} not for SINK. Removing.")
                    packets_to_remove_from_buffer.append(packet)
                    continue
                
                logging.info(f"R{self.current_round}: Sensor {s_id} (active) considering packet {packet.id} (src:{packet.source_id}) for SINK.")
                path_to_sink = find_shortest_path_to_sink_dijkstra_energy_aware(
                    self, s_id, self.sink_id, active_sensor_ids_for_routing
                )

                sensor_obj = self.get_sensor(s_id)
                
                if path_to_sink and len(path_to_sink) > 1:
                    if sensor_obj:
                        sensor_obj.parent_to_sink = path_to_sink[1]
                    next_hop_id = path_to_sink[1]
                    packet.next_hop_id = next_hop_id
                    
                    logging.info(f"R{self.current_round} Sensor {s_id} routing Packet {packet.id} (src: {packet.source_id}) to next_hop: {next_hop_id} via Dijkstra. Path: {path_to_sink}")
                    
                    sent_successfully, status_msg = self.communication_manager.send_packet(
                        sender_id=s_id, packet=packet, receiver_id=next_hop_id
                    )

                    if sent_successfully:
                        packets_to_remove_from_buffer.append(packet)
                        logging.info(f"  Packet {packet.id} successfully sent from {s_id} to {next_hop_id}. Status: {status_msg}")
                        if next_hop_id == self.sink_id:
                            self.total_packets_delivered_to_sink += 1
                            self.total_latency += (self.current_round - packet.creation_time + packet.latency) 
                            logging.info(f"  Packet {packet.id} DELIVERED TO SINK {self.sink_id}. Total delivered: {self.total_packets_delivered_to_sink}, Latency for this packet: {(self.current_round - packet.creation_time + packet.latency)}")
                    else:
                        logging.warning(f"  Packet {packet.id} send from {s_id} to {next_hop_id} FAILED. Reason: {status_msg}. Packet remains in buffer.")
                else:
                    if sensor_obj:
                        sensor_obj.parent_to_sink = None # Jeśli nie ma ścieżki, wyczyść rodzica
                    logging.warning(f"R{self.current_round} NO Dijkstra PATH from sensor {s_id} for packet {packet.id} (src:{packet.source_id}). Active set: {active_sensor_ids_for_routing}")
            
            sensor_obj.data_buffer = [p for p in sensor_obj.data_buffer if p not in packets_to_remove_from_buffer]    

    def calculate_q_coverage(self) -> float:
        """
        Oblicza wskaźnik Q-pokrycia sieci dla wymaganego poziomu k-pokrycia.

        Wskaźnik Q-pokrycia to stosunek liczby POI, które są pokryte przez co
        najmniej `self.k_coverage_level` *aktywnych i nieuszkodzonych* sensorów,
        do całkowitej liczby POI w sieci.

        Returns:
            float: Wartość Q-pokrycia [0.0, 1.0]. Zwraca 1.0, jeśli w sieci nie ma POI.
        """
        if not self.pois: return 1.0
        logging.debug(f"R{self.current_round} calculate_q_coverage: Entered. self.pois contains {len(self.pois)} POIs: {[p.id for p in self.pois]}. self.k_coverage_level={self.k_coverage_level}")

        pois_meeting_k_coverage = 0
        
        for poi_obj in self.pois:
            if len(poi_obj.covered_by_sensors) >= self.k_coverage_level:
                pois_meeting_k_coverage +=1
        
        return pois_meeting_k_coverage / len(self.pois) if len(self.pois) > 0 else 1.0

    def _get_neighbor_lists_for_stats(self) -> dict:
        """
        Pomocnicza funkcja do zbierania list ID potencjalnych sąsiadów
        dla wszystkich żywych sensorów (nie martwych/uszkodzonych).

        Ta metoda jest używana w `collect_round_statistics` do generowania
        danych o topologii sieci dla raportu statystyk.

        Returns:
            dict[int, list[int]]: Słownik {id_sensora: [lista_id_sąsiadów]}.
        """
        neighbor_lists = {}
        for s_id, sensor in self.sensors.items():
            if not sensor.is_failed and sensor.state != SensorState.DEAD:
                neighbor_lists[s_id] = [
                    n.id for n in sensor.neighbors 
                    if not n.is_failed and n.state != SensorState.DEAD
                ]
        return neighbor_lists
    
    def get_network_lifetime(self):
        """
        Oblicza żywotność sieci jako liczbę rund do momentu, gdy sieć
        przestaje być funkcjonalna (np. utrata pokrycia wszystkich POI,
        brak aktywnych sensorów).

        Returns:
            int | None: Numer bieżącej rundy, jeśli sieć przestała być funkcjonalna W TEJ RUNDZIE,
                        w przeciwnym razie None.
        """
        if all(sensor.state == SensorState.DEAD for sensor in self.sensors.values()):
            return self.current_round

        active_sensors = [sensor for sensor in self.sensors.values() if sensor.state == SensorState.ACTIVE]
        if not active_sensors:
            return self.current_round

        return None
    
    def collect_round_statistics(self) -> dict:
        """
        Zbiera i zwraca słownik ze statystykami bieżącej rundy symulacji.

        Statystyki obejmują:
        - Numer rundy
        - Liczba aktywnych, uśpionych i martwych sensorów (bez sinka)
        - Średnia energia pozostała w żywych sensorach (bez sinka)
        - Wskaźnik Q-pokrycia sieci
        - Packet Delivery Ratio (PDR) - stosunek pakietów dostarczonych do sinka do wygenerowanych
        - Średnie opóźnienie pakietów dostarczonych do sinka
        - Energie pojedynczych sensorów (bez sinka)
        - Stany pojedynczych sensorów (bez sinka)
        - Prawdopodobieństwa P(ACTIVE) automatów uczących (bez sinka, dla żywych)
        - Szczegóły pokrycia każdego POI (liczba pokrywających sensorów, status k-pokrycia)
        - Listy potencjalnych sąsiadów dla każdego żywego sensora (dla analizy topologii)
        """
        
        # Filtrujemy sensory raz, aby uniknąć wielokrotnego iterowania
        # Lista wszystkich sensorów niebędących stacją bazową
        non_sink_sensors_list = [s for s_id, s in self.sensors.items() if not s.is_sink] # Użyj s_id, s dla pewności
        
        # Lista AKTYWNYCH sensorów
        active_non_sink_sensors_list = [
            s for s in non_sink_sensors_list # Iteruj po już przefiltrowanej liście
            if s.state == SensorState.ACTIVE and not s.is_failed
        ]
        # Lista UŚPIONYCH sensorów
        sleep_non_sink_sensors_list = [
            s for s in non_sink_sensors_list # Iteruj po już przefiltrowanej liście
            if s.state == SensorState.SLEEP and not s.is_failed
        ]
        # Lista MARTWYCH lub USZKODZONYCH sensorów
        dead_or_failed_sensors_list = [
            s for s_id, s in self.sensors.items() # Iteruj po wszystkich sensorach
            if s.state == SensorState.DEAD or s.is_failed
        ]

        active_sensors_count = len(active_non_sink_sensors_list)
        sleep_sensors_count = len(sleep_non_sink_sensors_list)
        dead_sensors_count = len(dead_or_failed_sensors_list)

        num_alive_non_sink_sensors = active_sensors_count + sleep_sensors_count
        
        logging.debug(f"Corrected Calculation: num_alive_non_sink_sensors = {num_alive_non_sink_sensors} (type: {type(num_alive_non_sink_sensors)})")
        assert isinstance(num_alive_non_sink_sensors, int), \
            f"CRITICAL: num_alive_non_sink_sensors MUST be an integer, got {type(num_alive_non_sink_sensors)}"

        average_energy_alive_non_sink = 0.0
        sum_energy_alive_non_sink = 0.0

        if num_alive_non_sink_sensors > 0:
            current_energies_to_sum = []
            for s_list_type in [active_non_sink_sensors_list, sleep_non_sink_sensors_list]:
                for s_check in s_list_type:
                    assert isinstance(s_check.current_energy, (int, float)), \
                        f"Sensor {s_check.id} current_energy is not a number: {s_check.current_energy} (type {type(s_check.current_energy)})"
                    current_energies_to_sum.append(s_check.current_energy)
            
            if current_energies_to_sum:
                sum_energy_alive_non_sink = sum(current_energies_to_sum)
                average_energy_alive_non_sink = sum_energy_alive_non_sink / num_alive_non_sink_sensors
        
        poi_coverage = self.calculate_q_coverage()
    
        pdr_value = 0.0
        if self.total_packets_generated > 0:
            pdr_value = self.total_packets_delivered_to_sink / self.total_packets_generated

        avg_latency_value = 0.0
        if self.total_packets_delivered_to_sink > 0:
            avg_latency_value = self.total_latency / self.total_packets_delivered_to_sink

        stats = {
            "round": self.current_round,
            "active_sensors": active_sensors_count,
            "sleep_sensors": sleep_sensors_count,
            "dead_sensors": dead_sensors_count,
            "avg_energy_alive_non_sink": average_energy_alive_non_sink,
            "coverage_q_k": poi_coverage,
            "pdr": pdr_value,
            "avg_latency": avg_latency_value,
            "sensor_energies": {s.id: s.current_energy for s_id, s in self.sensors.items() if not s.is_sink},
            "sensor_states": {s.id: s.state for s_id, s in self.sensors.items() if not s.is_sink},
            "sensor_la_prob_active": { 
                s.id: (s.la.action_probabilities[Sensor.ACTION_ACTIVE_IDX] if s.la else -1.0)
                for s_id, s in self.sensors.items() if not s.is_sink and s.state != SensorState.DEAD and not s.is_failed
            },
            "poi_coverage_details": { 
                p.id: (len(p.covered_by_sensors), len(p.covered_by_sensors) >= self.k_coverage_level)
                for p in self.pois
            },
            "neighbor_lists": self._get_neighbor_lists_for_stats()
        }
    
        return stats
