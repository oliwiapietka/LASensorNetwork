# deployment_optimizer.py
"""
Moduł implementujący Algorytm Genetyczny (GA) do optymalizacji rozmieszczenia
sensorów w obszarze symulacji.

Celem optymalizacji jest znalezienie pozycji sensorów, które maksymalizują
funkcję oceny (fitness), typowo opartą o pokrycie punktów zainteresowania (POI)
oraz łączność sensorów pokrywających ze stacją bazową (sink).
"""
import random
import collections
import math
import logging
from simulation_core.sensor import Sensor
from simulation_core.poi import POI

class GADeploymentOptimizer:
    """
    Klasa realizująca Algorytm Genetyczny do optymalizacji rozmieszczenia sensorów.

    GA pracuje na populacji "chromosomów", gdzie każdy chromosom reprezentuje
    zbiór współrzędnych (x, y) dla wszystkich sensorów. Ewolucja populacji
    (selekcja, krzyżowanie, mutacja) kieruje się funkcją oceny (fitness),
    która quantyfikuje jakość danego rozmieszczenia.
    """
    def __init__(self, ga_config_params, network_layout_config, sensor_default_params,
                 poi_initial_configs, k_coverage_target, num_sensors_total, sink_id_to_assign):
        """
        Konstruktor klasy GADeploymentOptimizer.

        Inicjalizuje parametry algorytmu genetycznego oraz dane wejściowe
        dotyczące sieci (wymiary, parametry sensorów, POI), celu pokrycia
        i roli stacji bazowej.

        Args:
            ga_config_params (dict): Słownik zawierający parametry konfiguracji GA
                                     (np. 'population_size', 'generations',
                                     'mutation_rate', 'crossover_rate',
                                     'tournament_size', 'elitism_count').
                                     Odczytywane z sekcji [DeploymentOptimizer] w pliku config.
            network_layout_config (dict): Słownik z konfiguracją obszaru sieci
                                         (np. 'area_width', 'area_height').
                                         Odczytywane z sekcji [General].
            sensor_default_params (dict): Słownik z domyślnymi parametrami sensorów
                                         (np. 'comm_range', 'sensing_range').
                                         Odczytywane z sekcji [SensorDefaults].
            poi_initial_configs (list[dict]): Lista słowników konfiguracji dla każdego POI
                                             ({id, x, y}). Odczytywane z sekcji [POIs].
            k_coverage_target (int): Wymagany poziom k-pokrycia dla każdego POI.
                                    Odczytywane z sekcji [NetworkLogic].
            num_sensors_total (int): Całkowita liczba sensorów, których pozycje mają być zoptymalizowane.
                                     Odczytywane z sekcji [Sensors].
            sink_id_to_assign (int): Indeks (od 0 do num_sensors_total-1) w chromosomie,
                                   który reprezentuje sensor pełniący rolę stacji bazowej (sink).
                                   Ważne, jak ten indeks mapuje się na rzeczywiste ID sensorów.
                                   W tym modelu, zakładamy proste mapowanie indeksu GA na ID 0..N-1.
                                   Odczytywane z sekcji [General] ('sink_id').
        """
        self.pop_size = ga_config_params.getint('population_size', fallback=30)
        self.generations = ga_config_params.getint('generations', fallback=50)
        self.mutation_rate = ga_config_params.getfloat('mutation_rate', fallback=0.1)
        self.crossover_rate = ga_config_params.getfloat('crossover_rate', fallback=0.7)
        self.tournament_size = ga_config_params.getint('tournament_size', fallback=3)
        self.elitism_count = ga_config_params.getint('elitism_count', fallback=1)

        self.width = network_layout_config.getfloat('area_width')
        self.height = network_layout_config.getfloat('area_height')
        
        self.sensor_comm_range = sensor_default_params.getfloat('comm_range')
        self.sensor_sensing_range = sensor_default_params.getfloat('sensing_range')

        self.pois = []
        for idx, p_conf in enumerate(poi_initial_configs):
            self.pois.append(POI(id=p_conf.get('id', idx), x=p_conf['x'], y=p_conf['y']))

        self.k_coverage_target = k_coverage_target
        self.num_sensors = num_sensors_total
        self.sink_id_assigned_idx = sink_id_to_assign # Indeks w chromosomie, który reprezentuje stacje bazową (sink)

        self.population = []
        logging.info(f"GA Optimizer initialized: Pop={self.pop_size}, Gens={self.generations}, "
                     f"NumSensors={self.num_sensors}, SinkIdx={self.sink_id_assigned_idx}, #POIs={len(self.pois)}")

    def _create_individual(self) -> list[float]:
        """
        Tworzy pojedynczego osobnika (chromosom), reprezentującego losowe rozmieszczenie sensorów.

        Chromosom jest płaską listą współrzędnych: [s0_x, s0_y, s1_x, s1_y, ..., s(N-1)_x, s(N-1)_y].
        Współrzędne są losowane jednolicie w granicach obszaru symulacji.

        Returns:
            list[float]: Nowo utworzony chromosom (lista współrzędnych).
        """
        individual = []
        for i in range(self.num_sensors):
            individual.extend([random.uniform(0, self.width), random.uniform(0, self.height)])
        return individual

    def _initialize_population(self):
        """
        Inicjalizuje początkową populację osobników (chromosomów).

        Populacja składa się z `pop_size` losowo wygenerowanych chromosomów.
        """
        self.population = [self._create_individual() for _ in range(self.pop_size)]

    def _calculate_fitness(self, individual_flat_coords: list[float]) -> float:
        """
        Oblicza ocenę (fitness) dla danego osobnika (chromosomu).

        Funkcja oceny mierzy jakość rozmieszczenia sensorów reprezentowanego przez
        chromosom. W tym przypadku fitness zależy od dwóch głównych komponentów:
        1. Pokrycie punktów zainteresowania (POI) - ile POI spełnia wymagane k-pokrycie.
        2. Łączność sensorów pokrywających POI ze stacją bazową (sink).

        Fitness jest obliczany poprzez tymczasowe utworzenie obiektów Sensor i POI
        na podstawie współrzędnych z chromosomu i sprawdzenie ich wzajemnych relacji.

        Args:
            individual_flat_coords (list[float]): Chromosom, płaska lista współrzędnych
                                                 sensorów [s0_x, s0_y, s1_x, s1_y, ...].

        Returns:
            float: Obliczona ocena fitness dla danego chromosomu. Wyższa wartość oznacza lepsze rozmieszczenie.
        """        
        temp_sensor_objects: dict[int, Sensor] = {} # id_chromosomu -> obiekt Sensor
        sink_obj_eval: Sensor | None = None

        for i in range(self.num_sensors):
            x = individual_flat_coords[i * 2]
            y = individual_flat_coords[i * 2 + 1]
            
            is_this_the_sink = (i == self.sink_id_assigned_idx)
            s = Sensor(id=i, x=x, y=y, 
                       initial_energy=1.0,
                       comm_range=self.sensor_comm_range, 
                       sensing_range=0 if is_this_the_sink else self.sensor_sensing_range,
                       sink_id=self.sink_id_assigned_idx if is_this_the_sink else -1
                      )
            if is_this_the_sink:
                s.is_sink = True
                sink_obj_eval = s
            
            temp_sensor_objects[i] = s
        
        if not sink_obj_eval:
            logging.error("GA Fitness: Sink object not created from chromosome!")
            return 0.0 

        # Komponent 1: Pokrycie POI
        num_pois_k_covered = 0
        if self.pois:
            for poi_obj in self.pois:
                sensors_covering_this_poi = 0
                for s_id, sensor_obj in temp_sensor_objects.items():
                    if not sensor_obj.is_sink and sensor_obj.can_sense_poi(poi_obj):
                        sensors_covering_this_poi += 1
                if sensors_covering_this_poi >= self.k_coverage_target:
                    num_pois_k_covered += 1
            coverage_score_norm = num_pois_k_covered / len(self.pois)
        else: # Brak POI do pokrycia
            coverage_score_norm = 1.0 
        
        # Komponent 2: Łączność sensorów pokrywających POI ze stacją bazową
        # Identyfikuj sensory, które faktycznie pokrywają POI (do poziomu k_coverage)
        essential_covering_sensor_ids = set()
        if self.pois:
            for poi_obj in self.pois:
                actual_coverers_for_this_poi = []
                for s_id, sensor_obj in temp_sensor_objects.items():
                    if not sensor_obj.is_sink and sensor_obj.can_sense_poi(poi_obj):
                        actual_coverers_for_this_poi.append(s_id)
                
                if len(actual_coverers_for_this_poi) >= self.k_coverage_target:
                    essential_covering_sensor_ids.update(actual_coverers_for_this_poi)

        num_connected_covering_sensors = 0
        # Zbuduj graf tylko z sensorów w `temp_sensor_objects`
        adj = {s_id: [] for s_id in temp_sensor_objects}
        for i in temp_sensor_objects:
            for j in temp_sensor_objects:
                if i >= j: continue
                s1 = temp_sensor_objects[i]
                s2 = temp_sensor_objects[j]
                if s1.can_communicate_with(s2):
                    adj[s1.id].append(s2.id)
                    adj[s2.id].append(s1.id)
        
        if not essential_covering_sensor_ids:
            connectivity_score_norm = 1.0
        else:
            for s_id_coverer in essential_covering_sensor_ids:
                if s_id_coverer == self.sink_id_assigned_idx:
                    num_connected_covering_sensors +=1
                    continue

                # BFS do sprawdzenia ścieżki od s_id_coverer do stacji bazowej
                q = collections.deque([s_id_coverer])
                visited_bfs = {s_id_coverer}
                path_found = False
                while q:
                    u = q.popleft()
                    if u == self.sink_id_assigned_idx:
                        path_found = True
                        break
                    for v_neighbor_id in adj.get(u, []):
                        if v_neighbor_id not in visited_bfs:
                            visited_bfs.add(v_neighbor_id)
                            q.append(v_neighbor_id)
                if path_found:
                    num_connected_covering_sensors +=1
            connectivity_score_norm = num_connected_covering_sensors / len(essential_covering_sensor_ids)

        # Funkcja oceny (Fitness)
        # Priorytet: pełne pokrycie, potem pełna łączność
        fitness = coverage_score_norm * 1000.0 
        if coverage_score_norm >= 0.9999: # Jeśli pokrycie jest (prawie) pełne
            fitness += connectivity_score_norm * 100.0
        
        return fitness

    def _selection(self, population_with_fitness: list[tuple[list[float], float]]):
        """
        Implementuje selekcję osobników do roli rodziców dla następnej generacji.

        Wykorzystuje metodę selekcji turniejowej:
        Wielokrotnie wybiera losowo `tournament_size` osobników z populacji,
        a najlepszy osobnik z każdego turnieju zostaje wybrany jako rodzic.

        Args:
            population_with_fitness (list[tuple[list[float], float]]): Lista tupli,
                                                                        gdzie każda tupla
                                                                        zawiera chromosom
                                                                        i jego obliczoną ocenę fitness.

        Returns:
            list[list[float]]: Lista chromosomów wybranych jako rodzice. Rozmiar listy
                               jest równy rozmiarowi populacji (`self.pop_size`).
        """
        selected_parents = []
        for _ in range(len(population_with_fitness)):
            tournament = random.sample(population_with_fitness, self.tournament_size)
            winner = max(tournament, key=lambda item: item[1]) # item[0] to chromosom, item[1] to fitness
            selected_parents.append(winner[0]) # Dodaj sam chromosom
        return selected_parents

    def _crossover(self, parent1: list[float], parent2: list[float]):
        """
        Implementuje operację krzyżowania jednopunktowego (one-point crossover).

        Z prawdopodobieństwem `self.crossover_rate`, losowo wybierany jest
        punkt cięcia w chromosomie, a fragmenty rodziców są wymieniane,
        tworząc dwoje potomstwa. Operacja odbywa się na parach współrzędnych (genach).

        Args:
            parent1 (list[float]): Chromosom pierwszego rodzica.
            parent2 (list[float]): Chromosom drugiego rodzica.

        Returns:
            tuple[list[float], list[float]]: Para chromosomów potomstwa.
        """
        child1, child2 = list(parent1), list(parent2)
        if random.random() < self.crossover_rate:
            # Krzyżowanie par współrzędnych (co 2 elementy w płaskiej liście)
            num_genes = len(parent1) // 2 # Liczba par (x,y)
            if num_genes > 1:
                point = random.randint(1, num_genes - 1) * 2 # Punkt cięcia musi być parzysty
                child1 = parent1[:point] + parent2[point:]
                child2 = parent2[:point] + parent1[point:]
        return child1, child2

    def _mutate(self, individual: list[float]):
        """
        Implementuje operację mutacji na pojedynczym chromosomie.

        Z prawdopodobieństwem `self.mutation_rate`, każda pojedyncza
        współrzędna (gen) w chromosomie może ulec mutacji. Mutacja polega
        na dodaniu niewielkiej, losowej wartości (z rozkładu normalnego)
        do współrzędnej, a następnie przycięciu jej do granic obszaru symulacji.

        Args:
            individual (list[float]): Chromosom (lista współrzędnych) do zmutowania.

        Returns:
            list[float]: Zmutowany chromosom.
        """
        mutated_individual = list(individual)
        for i in range(len(mutated_individual)):
            if random.random() < self.mutation_rate:
                # Zmiana o wartość z rozkładu normalnego, np. 5% szerokości/wysokości obszaru
                dimension_limit = self.width if i % 2 == 0 else self.height
                change = random.gauss(0, dimension_limit * 0.05) 
                mutated_individual[i] += change
                
                # Utrzymanie współrzędnych w granicach
                if i % 2 == 0: # Współrzędna X
                    mutated_individual[i] = max(0, min(self.width, mutated_individual[i]))
                else: # Współrzędna Y
                    mutated_individual[i] = max(0, min(self.height, mutated_individual[i]))
        return mutated_individual

    def run_optimization(self) -> list[dict] | None:
        """
        Uruchamia główny algorytm genetyczny do optymalizacji rozmieszczenia.

        Inicjalizuje populację, a następnie iteruje przez określoną liczbę generacji.
        W każdej generacji:
        1. Oblicza fitness dla wszystkich osobników.
        2. Sortuje populację według fitness.
        3. Zapisuje najlepszego osobnika znalezionego dotychczas.
        4. Wykonuje selekcję rodziców.
        5. Tworzy nową populację poprzez elityzm, krzyżowanie i mutację.
        Algorytm kończy działanie po osiągnięciu maksymalnej liczby generacji
        lub znalezieniu rozwiązania o wystarczająco wysokim fitness.

        Returns:
            list[dict] | None: Lista słowników reprezentujących zoptymalizowane
                               pozycje sensorów w formacie [{'id': ..., 'x': ..., 'y': ..., 'is_sink_role': ...}, ...],
                               gdzie ID odpowiada indeksowi w chromosomie (0 do N-1).
                               Zwraca None, jeśli nie udało się znaleźć żadnego osobnika
                               (np. błąd w inicjalizacji, choć mało prawdopodobne).
        """
        logging.info("Starting GA deployment optimization...")
        self._initialize_population()

        best_overall_fitness = -1.0
        best_overall_individual = None

        for gen in range(self.generations):
            population_with_fitness = []
            for individual in self.population:
                fitness = self._calculate_fitness(individual)
                population_with_fitness.append((individual, fitness))
            
            population_with_fitness.sort(key=lambda item: item[1], reverse=True) # Sortuj wg fitness
            
            current_gen_best_individual, current_gen_best_fitness = population_with_fitness[0]
            if current_gen_best_fitness > best_overall_fitness:
                best_overall_fitness = current_gen_best_fitness
                best_overall_individual = list(current_gen_best_individual)
            
            if (gen + 1) % 10 == 0 or gen == self.generations -1 : # Loguj co 10 generacji
                 logging.info(f"GA Gen: {gen+1}/{self.generations}, Best Fitness in Gen: {current_gen_best_fitness:.2f}, Overall Best Fitness: {best_overall_fitness:.2f}")

            if best_overall_fitness >= 1000.0 + 99.0 : # Jeśli osiągnięto pełne pokrycie i prawie pełną łączność
                logging.info(f"GA: High quality solution found at generation {gen+1}. Stopping early.")
                break

            selected_parents = self._selection(population_with_fitness) # Selekcja
            
            next_population = []
            # przenieś najlepszych osobników do następnej populacji
            for i in range(self.elitism_count):
                next_population.append(list(population_with_fitness[i][0]))

            while len(next_population) < self.pop_size:
                p1, p2 = random.sample(selected_parents, 2) # Wybierz dwóch różnych rodziców
                c1, c2 = self._crossover(p1, p2)
                next_population.append(self._mutate(c1))
                if len(next_population) < self.pop_size:
                    next_population.append(self._mutate(c2))
            
            self.population = next_population[:self.pop_size]

        logging.info(f"GA Finished. Best deployment fitness: {best_overall_fitness:.2f}")
        
        if best_overall_individual:
            optimized_deployment_config = []
            for i in range(self.num_sensors):
                x = best_overall_individual[i * 2]
                y = best_overall_individual[i * 2 + 1]
                is_sink_role = (i == self.sink_id_assigned_idx)
                optimized_deployment_config.append({
                    'id': i, # To ID jest indeksem 0..N-1. SimulationManager zmapuje je na ID z config.
                    'x': x,
                    'y': y,
                    'is_sink_role': is_sink_role # Flaga wskazująca, czy ten slot w chromosomie to sink
                })
            return optimized_deployment_config
        return None