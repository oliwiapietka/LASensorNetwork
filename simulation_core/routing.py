# simulation_core/routing.py
"""
Moduł implementujący algorytmy routingu w sieci sensorowej.

Zawiera funkcje do znajdowania ścieżek od sensorów do stacji bazowej
(sink) przez aktywne węzły sieci, uwzględniając różne metryki kosztu,
np. energię węzłów.
"""
import collections
from .network import Network
import heapq
from .sensor import SensorState
from .energy_model import EnergyConsumption
import logging

def find_shortest_path_to_sink_dijkstra_energy_aware(
    network: 'Network', # Użyj type hint jako string, jeśli Network jest w tym samym module lub import cykliczny
    start_node_id: int,
    sink_node_id: int,
    active_sensor_ids_for_path: set[int]
) -> list[int] | None:
    """
    Znajduje ścieżkę z `start_node_id` do `sink_node_id` w sieci,
    używając algorytmu Dijkstry z metryką kosztu uwzględniającą energię.

    Koszt przejścia z węzła A do węzła B (sąsiada) jest obliczany na podstawie
    odwrotności pozostałej energii węzła B (preferuje węzły z wyższą energią)
    oraz kosztu energetycznego transmisji z A do B.
    Algorytm bierze pod uwagę tylko sensory, których ID znajduje się w zbiorze
    `active_sensor_ids_for_path` jako potencjalne węzły pośrednie i docelowe
    (poza samym węzłem startowym, który musi być w tym zbiorze, chyba że jest sinkiem).

    Args:
        network ('Network'): Obiekt sieci, w której szukamy ścieżki.
        start_node_id (int): ID sensora startowego.
        sink_node_id (int): ID stacji bazowej (cel ścieżki).
        active_sensor_ids_for_path (set[int]): Zbiór ID sensorów (w tym sinka, jeśli ma być węzłem docelowym),
                                              które są uważane za aktywne i mogą być użyte jako węzły w ścieżce.

    Returns:
        list[int] | None: Lista ID sensorów tworzących ścieżkę od start_node_id do sink_node_id,
                          lub None, jeśli ścieżka nie istnieje.
    """
    start_node_obj = network.get_sensor(start_node_id)

    if not start_node_obj or start_node_obj.is_failed or \
       start_node_id not in active_sensor_ids_for_path:
        if start_node_id == sink_node_id and \
           network.get_sensor(sink_node_id) and \
           not network.get_sensor(sink_node_id).is_failed and \
           network.get_sensor(sink_node_id).state == SensorState.ACTIVE:
            return [start_node_id]
        logging.debug(f"Pathfind_Dijkstra: Start node {start_node_id} not valid for pathfinding.")
        return None

    if start_node_id == sink_node_id:
        return [start_node_id]

    # Kolejka priorytetowa: (koszt_dojścia, id_węzła, ścieżka_do_węzła)
    priority_queue = [(0, start_node_id, [start_node_id])]
    # Słownik przechowujący minimalny koszt dotarcia do danego węzła
    min_costs = {s_id: float('inf') for s_id in network.sensors}
    min_costs[start_node_id] = 0

    W_ENERGY_NODE = 1.0  # Waga dla pozostałej energii następnego węzła
    W_TX_COST = 0.1      # Waga dla kosztu transmisji (mniejsza waga, jeśli energia jest ważniejsza)

    while priority_queue:
        current_cost, current_node_id, current_path = heapq.heappop(priority_queue)

        if current_node_id == sink_node_id:
            logging.debug(f"Pathfind_Dijkstra: Path found from {start_node_id} to {sink_node_id}: {current_path} with cost {current_cost:.2f}")
            return current_path

        # Jeśli znaleźliśmy już lepszą ścieżkę do tego węzła, pomiń
        if current_cost > min_costs[current_node_id]:
            continue

        current_sensor_obj = network.get_sensor(current_node_id)
        if not current_sensor_obj: continue

        for neighbor_obj in current_sensor_obj.neighbors:
            if neighbor_obj.id in active_sensor_ids_for_path and not neighbor_obj.is_failed:
                # Obliczanie kosztu krawędzi
                cost_component_energy = 0
                if neighbor_obj.current_energy > 1e-6: # Unikaj dzielenia przez zero lub bardzo małą energię
                    # Im więcej energii, tym mniejszy koszt
                    cost_component_energy = 1.0 / neighbor_obj.current_energy
                else: # Duży koszt, jeśli sąsiad ma prawie zerową energię
                    cost_component_energy = float('inf')

                cost_component_tx = EnergyConsumption.communication_tx_cost(
                    current_sensor_obj.distance_to(neighbor_obj.pos)
                )

                edge_cost = (W_ENERGY_NODE * cost_component_energy) + (W_TX_COST * cost_component_tx)
                
                new_cost_to_neighbor = current_cost + edge_cost

                if new_cost_to_neighbor < min_costs.get(neighbor_obj.id, float('inf')):
                    min_costs[neighbor_obj.id] = new_cost_to_neighbor
                    new_path = list(current_path)
                    new_path.append(neighbor_obj.id)
                    heapq.heappush(priority_queue, (new_cost_to_neighbor, neighbor_obj.id, new_path))
    
    logging.debug(f"Pathfind_Dijkstra: No path found from {start_node_id} to {sink_node_id} via active set.")
    return None