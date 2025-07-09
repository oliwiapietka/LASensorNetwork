# simulation_core/poi.py
"""
Moduł definiujący klasę POI (Point of Interest).

Klasa POI reprezentuje punkt zainteresowania w sieci sensorowej,
który wymaga monitorowania/pokrycia przez sensory. Przechowuje
informacje o identyfikatorze, pozycji, poziomie krytyczności oraz
statusie pokrycia przez aktywne sensory.
"""

class POI:
    """
    Reprezentuje punkt zainteresowania (POI) w obszarze symulacji.

    POI to cel, który sensory mają za zadanie wykrywać i monitorować.
    """
    def __init__(self, id, x, y, critical_level=1):
        """
        Konstruktor klasy POI.

        Inicjalizuje POI z unikalnym identyfikatorem, pozycją i poziomem krytyczności.

        Args:
            id (int): Unikalny identyfikator POI.
            x (float): Współrzędna X pozycji POI.
            y (float): Współrzędna Y pozycji POI.
            critical_level (int): Poziom krytyczności/ważności POI (domyślnie 1).
                                  Może być używany do priorytetyzacji pokrycia.
        """
        self.id = id
        self.pos = (x, y)
        self.critical_level = critical_level
        self.is_covered = False
        self.covered_by_sensors = set()

    def update_coverage_status(self, active_sensors_covering):
        """
        Aktualizuje status pokrycia POI na podstawie zbioru aktywnych sensorów,
        które go aktualnie pokrywają sensorycznie.

        POI jest uznawane za 'covered' (self.is_covered = True), jeśli liczba
        aktywnych sensorów w zbiorze `active_sensors_covering` jest większa lub
        równa wymaganemu poziomowi k-pokrycia (`k_level`).

        Args:
            active_sensors_covering (set[int]): Zbiór ID sensorów, które w bieżącej
                                                rundzie są w stanie ACTIVE, nieuszkodzone
                                                i w zasięgu sensorycznym tego POI.
            k_level (int): Wymagany poziom k-pokrycia dla tego POI (domyślnie 1).
        """
        self.covered_by_sensors = active_sensors_covering
        self.is_covered = len(self.covered_by_sensors) > 0

    def __repr__(self):
        """
        Zwraca reprezentację obiektu POI jako string (do celów debugowania/logowania).
        """
        return f"POI(id={self.id}, pos={self.pos}, covered={self.is_covered})"