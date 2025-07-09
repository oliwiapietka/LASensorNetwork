# simulation_core/sensor.py
"""
Moduł definiujący klasy Sensor, LearningAutomaton oraz Enum SensorState.

Zawiera implementację pojedynczego węzła sensorowego w symulacji,
jego stany (ACTIVE, SLEEP, DEAD), zarządzanie energią, zasięgiem,
buforem danych oraz interakcję z automatem uczącym (LA) do
podejmowania decyzji o stanie aktywności. Moduł zawiera również
klasę LearningAutomaton realizującą schemat uczenia L_R-I.
"""
import random
import math
import logging
from .energy_model import EnergyConsumption
from typing import Union

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# LearningAutomaton (L_R-I)
class LearningAutomaton:
    """
    Implementacja automatu uczącego (Learning Automaton) typu L_R-I
    (Linear Reward-Inaction) dla dwóch akcji: ACTIVE i SLEEP.

    Automat uczący służy sensorowi do dynamicznego dostosowywania
    prawdopodobieństwa wyboru akcji na podstawie otrzymywanych nagród
    (lub braku kary, w przypadku Inaction).
    """
    def __init__(self, num_actions=2, learning_rate_reward_A=0.1):
        """
        Konstruktor klasy LearningAutomaton.

        Inicjalizuje automat uczący z określoną liczbą akcji i parametrem uczenia 'a'.

        Args:
            num_actions (int): Liczba dostępnych akcji (domyślnie 2: ACTIVE, SLEEP).
                               Ta implementacja wspiera tylko 2 akcje.
            learning_rate_reward_A (float): Parametr uczenia 'a' dla nagród
                                           (musi być w zakresie (0, 1)).
        """
        assert num_actions == 2, "LearningAutomaton tylko dla 2 akcji (ACTIVE, SLEEP)."
        self.num_actions = num_actions
        self.a_param = learning_rate_reward_A
        self.action_probabilities = [0.5, 0.5]
        self.chosen_action_index = None

    def set_probabilities_based_on_energy_ratio(self, energy_ratio: float):
        """
        Ustawia prawdopodobieństwa wyboru akcji ACTIVE/SLEEP na podstawie
        aktualnego wskaźnika energii sensora.

        Prawdopodobieństwo bycia ACTIVE jest ustawiane proporcjonalnie do
        wskaźnika energii (pozostała energia sensora / całkowita energia sieci),
        a prawdopodobieństwo bycia SLEEP jest dopełnieniem do 1.0.

        Args:
            energy_ratio (float): Wskaźnik energii sensora, wartość w zakresie [0.0, 1.0].
                                  Obliczana w klasie Network (faza Learning).
        """
        prob_active = max(0.0, min(1.0, energy_ratio))
        self.action_probabilities[0] = prob_active
        self.action_probabilities[1] = 1.0 - prob_active
        self._normalize_and_clip()
    
    def choose_action(self) -> int:
        """
        Wybiera akcję (ACTIVE lub SLEEP) na podstawie aktualnych prawdopodobieństw.

        Wykorzystuje ważony losowy wybór spośród dostępnych akcji.

        Returns:
            int: Indeks wybranej akcji (0 dla ACTIVE, 1 dla SLEEP).
        """
        self._normalize_and_clip()
        self.chosen_action_index = random.choices(
            range(self.num_actions),
            weights=self.action_probabilities,
            k=1
        )[0]
        return self.chosen_action_index

    def update_probabilities_LRI(self, chosen_action_idx: int, is_reward_signal: bool):
        """
        Aktualizuje prawdopodobieństwa wyboru akcji zgodnie ze schematem L_R-I.

        Aktualizacja następuje tylko w przypadku otrzymania sygnału nagrody (`is_reward_signal` == True).
        Zgodnie ze schematem L_R-I, tylko prawdopodobieństwo nagrodzonej akcji rośnie,
        a prawdopodobieństwa pozostałych akcji maleją (proporcjonalnie).
        W tej implementacji, nagroda (jeśli występuje) jest ZAWSZE za akcję ACTIVE.

        Args:
            chosen_action_idx (int): Indeks akcji, która "została podjęta"
                                     i jest oceniana (dla algorytmu CS, to akcja ACTIVE sensora).
                                     Teoretycznie może być użyty do nagradzania innych akcji,
                                     ale w tym kontekście nagradzamy tylko bycie ACTIVE.
            is_reward_signal (bool): True, jeśli sensor otrzymał sygnał nagrody
                                     (np. za bycie częścią dobrego CS); False w przeciwnym razie.
        """
        if not is_reward_signal:
            return

        action_to_reward_idx = Sensor.ACTION_ACTIVE_IDX # Zawsze nagradzamy akcję ACTIVE
        
        if chosen_action_idx != action_to_reward_idx:
            logging.warning(f"LA Update: Rewarding action {chosen_action_idx}, but expected to reward ACTION_ACTIVE_IDX {action_to_reward_idx}.")

        other_action_idx = Sensor.ACTION_SLEEP_IDX

        current_prob_rewarded = self.action_probabilities[action_to_reward_idx]
        current_prob_other = self.action_probabilities[other_action_idx]

        # Formuła aktualizacji prawdopodobieństw dla L_R-I (jeśli jest nagroda):
        # Prawdopodobieństwo nagrodzonej akcji rośnie: p_i(t+1) = p_i(t) + a * (1 - p_i(t))
        self.action_probabilities[action_to_reward_idx] = current_prob_rewarded + \
                                                          self.a_param * (1.0 - current_prob_rewarded)
        # Prawdopodobieństwa pozostałych akcji maleją proporcjonalnie: p_j(t+1) = p_j(t) - a * p_j(t)
        self.action_probabilities[other_action_idx] = current_prob_other - \
                                                      self.a_param * current_prob_other
        
        self._normalize_and_clip()

    def _normalize_and_clip(self):
        """
        Normalizuje sumę prawdopodobieństw do 1.0 i przycina wartości,
        aby mieściły się w zakresie [min_prob, 1 - min_prob].

        Zapobiega to zbieganiu prawdopodobieństw do 0 lub 1 zbyt szybko.
        Minimalne prawdopodobieństwo zapewnia, że każda akcja ma zawsze
        pewną (choćby małą) szansę na wybór.
        """
        min_prob = 0.001
        p0 = self.action_probabilities[Sensor.ACTION_ACTIVE_IDX]
        p1 = self.action_probabilities[Sensor.ACTION_SLEEP_IDX]

        # Krok 1: Upewnij się, że indywidualne prawdopodobieństwa są w zakresie [0, 1]
        p0 = max(0.0, min(1.0, p0))
        p1 = max(0.0, min(1.0, p1))
        
        # Krok 2: Normalizacja sumy do 1.0
        current_total_prob = p0 + p1
        if abs(current_total_prob - 1.0) > 1e-9: # Jeśli suma znacząco odbiega od 1
            if current_total_prob == 0:
                self.action_probabilities = [0.5] * self.num_actions
            else:
                self.action_probabilities[Sensor.ACTION_ACTIVE_IDX] = p0 / current_total_prob
                self.action_probabilities[Sensor.ACTION_SLEEP_IDX] = p1 / current_total_prob
        else:
            self.action_probabilities[Sensor.ACTION_ACTIVE_IDX] = p0
            self.action_probabilities[Sensor.ACTION_SLEEP_IDX] = p1

        # Krok 3: Zastosuj min_prob, zachowując sumę równą 1
        if self.action_probabilities[Sensor.ACTION_ACTIVE_IDX] < min_prob:
            self.action_probabilities[Sensor.ACTION_ACTIVE_IDX] = min_prob
            self.action_probabilities[Sensor.ACTION_SLEEP_IDX] = 1.0 - min_prob
        elif self.action_probabilities[Sensor.ACTION_SLEEP_IDX] < min_prob: # elif jest kluczowe
            self.action_probabilities[Sensor.ACTION_SLEEP_IDX] = min_prob
            self.action_probabilities[Sensor.ACTION_ACTIVE_IDX] = 1.0 - min_prob
        
        # Ostateczne sprawdzenie i ewentualna normalizacja (głównie na wypadek, gdyby min_prob > 0.5)
        final_sum = sum(self.action_probabilities)
        if abs(final_sum - 1.0) > 1e-9:
            if final_sum == 0: self.action_probabilities = [0.5] * self.num_actions
            else: self.action_probabilities = [p / final_sum for p in self.action_probabilities]

    def initialize_probabilities(self):
        """
        Resetuje prawdopodobieństwa wyboru akcji do wartości początkowych (np. 0.5 dla każdej akcji).

        Wywoływana w fazie Network Setup na początku symulacji.
        """
        self.action_probabilities = [0.5, 0.5]  # Reset probabilities to default values
        self.chosen_action_index = None  # Reset chosen action index

class SensorState:
    ACTIVE = "ACTIVE"
    SLEEP = "SLEEP"
    DEAD = "DEAD"

class Sensor:
    """
    Reprezentuje pojedynczy węzeł sensorowy w sieci WSN.

    Klasa Sensor przechowuje informacje o identyfikatorze sensora,
    jego pozycji, poziomie energii, zasięgach komunikacji i wykrywania.
    Zarządza stanem operacyjnym sensora (ACTIVE, SLEEP, DEAD), buforem
    danych oraz interakcją z przypisanym automatem uczącym (Learning Automaton)
    do podejmowania decyzji o stanie aktywności w każdej rundzie.
    """
    # Definicje indeksów akcji dla LA
    ACTION_ACTIVE_IDX = 0
    ACTION_SLEEP_IDX = 1

    def __init__(self, id, x, y, initial_energy, comm_range, sensing_range, sink_id=None,
                 learning_rate_reward_A=0.1):
        """
        Konstruktor klasy Sensor.

        Inicjalizuje sensor z podstawowymi parametrami fizycznymi i energetycznymi.
        Przypisywana jest mu rola stacji bazowej (sink) lub zwykłego sensora.
        Zwykłym sensorom przypisywany jest automat uczący.

        Args:
            id (int): Unikalny identyfikator sensora.
            x (float): Współrzędna X pozycji sensora.
            y (float): Współrzędna Y pozycji sensora.
            initial_energy (float): Początkowy poziom energii sensora.
            comm_range (float): Zasięg komunikacji sensora.
            sensing_range (float): Zasięg sensoryczny (wykrywania) sensora.
            sink_id (int | None): ID stacji bazowej. Jeśli ID sensora jest równe sink_id,
                                  sensor jest traktowany jako stacja bazowa (domyślnie None).
            learning_rate_reward_A (float): Parametr uczenia 'a' dla automatu LA tego sensora.
                                           Używane tylko dla sensorów niebędących sinkiem.
        """
        self.id = id
        self.pos = (x, y)
        self.initial_energy = initial_energy
        self.current_energy = initial_energy
        self.comm_range = comm_range
        self.sensing_range = sensing_range
        self.state = SensorState.SLEEP
        self.is_sink = (self.id == sink_id)
        self.is_critical_sensor = False
        self.neighbor_poi_coverage: dict[int, set[int]] = {}
        self.time_last_heard_from_neighbor: dict[int, int] = {}

        if self.is_sink:
            self.state = SensorState.ACTIVE
            self.current_energy = float('inf')

        self.la = LearningAutomaton(
            learning_rate_reward_A=learning_rate_reward_A
        ) if not self.is_sink else None

        if not self.is_sink and self.la is None:
            raise ValueError(f"Sensor {self.id} must have a Learning Automaton assigned.")
        
        self.last_la_action_idx = None

        self.neighbors = []
        self.monitored_pois = []
        self.parent_to_sink = None
        self.data_buffer = []
        self.is_failed = False
        self.is_critical_sensor = False

    def distance_to(self, target_pos_or_sensor):
        """
        Oblicza odległość Euclideanową do innego obiektu (sensora lub POI)
        lub do podanej pozycji (x, y).

        Args:
            target_pos_or_sensor (Union[tuple[float, float], 'Sensor']): Pozycja docelowa
                                                                         (x, y) lub obiekt
                                                                         posiadający atrybut `.pos`.

        Returns:
            float: Odległość między bieżącym sensorem a celem.
        """
        if hasattr(target_pos_or_sensor, 'pos'):
            target_pos = target_pos_or_sensor.pos
        else:
            target_pos = target_pos_or_sensor
        return math.sqrt((self.pos[0] - target_pos[0])**2 + (self.pos[1] - target_pos[1])**2)

    def can_communicate_with(self, other_sensor):
        """
        Sprawdza, czy bieżący sensor może potencjalnie komunikować się
        z innym sensorem.

        Potencjalna komunikacja jest możliwa, jeśli oba sensory nie są trwale
        uszkodzone i znajdują się w zasięgu komunikacji siebie nawzajem.
        Ta metoda nie sprawdza, czy sensor `other_sensor` jest w stanie ACTIVE
        (co jest wymagane do *rzeczywistego* odebrania pakietu), a jedynie
        fizyczną/topologiczną możliwość połączenia.

        Args:
            other_sensor ('Sensor'): Obiekt innego sensora do sprawdzenia.

        Returns:
            bool: True, jeśli potencjalna komunikacja jest możliwa, False w przeciwnym przypadku.
        """
        if other_sensor.is_failed or self.is_failed:
            return False
        return self.distance_to(other_sensor.pos) <= self.comm_range and self.id != other_sensor.id

    def can_sense_poi(self, poi):
        """
        Sprawdza, czy bieżący sensor może sensorycznie wykryć dany punkt POI.

        Wykrywanie jest możliwe, jeśli sensor nie jest trwale uszkodzony,
        nie jest martwy i POI znajduje się w jego zasięgu sensorycznym.
        Nie sprawdza, czy sensor jest w stanie ACTIVE (ta metoda określa
        *potencjał* wykrywania).

        Args:
            poi ('POI'): Obiekt punktu zainteresowania (POI) do sprawdzenia.

        Returns:
            bool: True, jeśli POI jest w zasięgu sensorycznym sensora, False w przeciwnym przypadku.
        """
        if self.is_failed or self.state == SensorState.DEAD:
            return False
        return self.distance_to(poi.pos) <= self.sensing_range

    def update_energy(self, activity_type=None, amount=None, duration=1.0):
        """
        Aktualizuje poziom energii sensora na podstawie zużycia.

        Energia może być zredukowana o stałą `amount` lub na podstawie
        zdefiniowanych kosztów energetycznych dla określonego typu aktywności
        i czasu trwania. Jeśli energia spadnie do zera lub poniżej, stan sensora
        zmienia się na DEAD.

        Args:
            activity_type (SensorState | str | None): Typ aktywności, która powoduje zużycie energii
                                                    (np. SensorState.ACTIVE, SensorState.SLEEP, "TRANSMIT", "RECEIVE", "PROCESSING").
                                                    Jeśli None i `amount` też None, zużycie zależy od aktualnego stanu.
            amount (float | None): Stała ilość energii do odjęcia. Jeśli podane,
                                   przesłania zużycie oparte na activity_type.
            duration (float): Czas trwania aktywności (domyślnie 1.0, np. reprezentuje 1 rundę).
        """
        if self.is_sink or self.state == SensorState.DEAD: return
        cost = 0
        if amount: cost = amount
        elif activity_type:
            if activity_type == SensorState.ACTIVE: cost = EnergyConsumption.MONITORING * duration
            elif activity_type == SensorState.SLEEP: cost = EnergyConsumption.SLEEP * duration
            elif activity_type == "PROCESSING": cost = EnergyConsumption.PROCESSING * duration
        else:
            if self.state == SensorState.ACTIVE: cost = EnergyConsumption.MONITORING * duration
            elif self.state == SensorState.SLEEP: cost = EnergyConsumption.SLEEP * duration
        self.current_energy -= cost
        if self.current_energy <= 0:
            self.current_energy = 0
            self.state = SensorState.DEAD

    def handle_broadcast_message(self, sender_id: int, message_type: str, payload: any, network_time: int):
        """
        Przetwarza otrzymaną wiadomość broadcastową od innego sensora.

        Sensory używają tego do aktualizacji swoich lokalnych informacji, np.
        o pokryciu POI przez sąsiadów (na podstawie komunikatów "POI_COVERAGE_ADVERTISEMENT").

        Args:
            sender_id (int): ID sensora, który wysłał wiadomość.
            message_type (str): Typ otrzymanej wiadomości (np. "POI_COVERAGE_ADVERTISEMENT").
            payload (any): Treść (ładunek) wiadomości.
            network_time (int): Aktualna runda symulacji (czas sieciowy),
                                w której wiadomość została odebrana.
        """
        if message_type == "POI_COVERAGE_ADVERTISEMENT":
            if isinstance(payload, dict) and 'covered_poi_ids' in payload:
                covered_ids = set(payload['covered_poi_ids'])
                self.neighbor_poi_coverage[sender_id] = covered_ids
                self.time_last_heard_from_neighbor[sender_id] = network_time
                # logging.debug(f"  Sensor {self.id} updated POI coverage from neighbor {sender_id}: {covered_ids}")
            else:
                logging.warning(f"Sensor {self.id} received malformed POI_COVERAGE_ADVERTISEMENT from {sender_id}")
        
        elif message_type == "NEIGHBOR_ANNOUNCEMENT":
            pass

    def __repr__(self):
        """
        Zwraca reprezentację sensora jako string (do celów debugowania/logowania).

        Pokazuje ID sensora, poziom energii, aktualny stan, informację
        czy jest sensorem krytycznym, prawdopodobieństwo P(ACTIVE) LA (jeśli posiada)
        oraz opcjonalnie ID pokrywanych POI (jeśli jest aktywny i coś pokrywa).
        """
        la_probs_str = ""
        if self.la:
            la_probs_str = f"LA_P(A):{self.la.action_probabilities[Sensor.ACTION_ACTIVE_IDX]:.2f}"
        crit_str = " CRIT" if self.is_critical_sensor else ""
        covered_pois_repr = ""
        if self.state == SensorState.ACTIVE and self.monitored_pois:
            monitored_ids = {p.id for p in self.monitored_pois}
            if monitored_ids:
                covered_pois_repr = f" COV:{monitored_ids}"
                
        return (f"Sensor(id={self.id}, E:{self.current_energy:.2f}, S:{self.state}{crit_str}{covered_pois_repr}, {la_probs_str})"
                if not self.is_sink else
                f"Sensor(id={self.id}, S:{self.state}) (SINK)")
