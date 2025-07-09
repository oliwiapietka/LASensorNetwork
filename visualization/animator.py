# visualization/animator.py
"""
Moduł odpowiedzialny za wizualizację stanu sieci sensorowej w czasie rzeczywistym
podczas przebiegu symulacji.

Wykorzystuje bibliotekę Matplotlib do rysowania pozycji sensorów i POI, ich
stanów (aktywny, uśpiony, martwy) oraz potencjalnych połączeń komunikacyjnych.
Umożliwia animowanie zmian stanu sieci runda po rundzie.
"""
import logging
logging.getLogger('matplotlib').setLevel(logging.WARNING)
import matplotlib.pyplot as plt
from simulation_core.sensor import SensorState # dla kolorów
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

plt.ion() # Włącz tryb interaktywny

class NetworkAnimator:
    """
    Klasa zarządzająca wizualizacją graficzną sieci sensorowej w trakcie symulacji.

    Tworzy okno wykresu Matplotlib i aktualizuje go w kolejnych rundach
    symulacji, pokazując pozycje, stany, zasięgi sensorów oraz POI.
    """
    def __init__(self, network, plot_interval=1):
        """
        Konstruktor klasy NetworkAnimator.

        Inicjalizuje figury i osie Matplotlib oraz przechowuje referencję
        do obiektu sieci, który ma być wizualizowany.

        Args:
            network_ref (Network): Referencja do obiektu Network, który zawiera
                                   stan sieci do wizualizacji.
            plot_interval (int): Liczba rund symulacji pomiędzy kolejnymi
                                 aktualizacjami wizualizacji. Aktualizacja następuje
                                 co `plot_interval` rund.
        """
        self.network = network
        self.plot_interval = plot_interval
        self.fig, self.ax = plt.subplots(figsize=(10, 10))
        self.sensor_nodes_plot = None
        self.poi_nodes_plot = None
        self.sink_marker_plot = None
        self.comm_range_circles = []
        self.sensing_range_circles = []
        self.comm_links_plot = []
        self.round_text = None

        self._setup_plot()
        self.fig.canvas.mpl_connect('close_event', self._handle_close)
        self.is_window_open = True

    def _handle_close(self, evt):
        self.is_window_open = False
        print("Animator window closed by user.")

    def _setup_plot(self):
        """
        Konfiguruje początkowe ustawienia wykresu Matplotlib.

        Ustawia tytuł wykresu, etykiety osi, granice obszaru rysowania
        oraz dodaje punkty zainteresowania (POI) do wykresu (są statyczne).
        """
        self.ax.set_xlim(0, self.network.width)
        self.ax.set_ylim(0, self.network.height)
        self.ax.set_aspect('equal', adjustable='box')
        self.ax.set_title("Wireless Sensor Network Simulation")
        self.ax.set_xlabel("X coordinate")
        self.ax.set_ylabel("Y coordinate")
        self.round_text = self.ax.text(0.02, 0.95, '', transform=self.ax.transAxes)

        # Wstępne narysowanie sensorów
        s_x = [s.pos[0] for s in self.network.sensors.values()]
        s_y = [s.pos[1] for s in self.network.sensors.values()]
        self.sensor_nodes_plot = self.ax.scatter(s_x, s_y, s=50, c='blue', edgecolors='black', zorder=3)

        if self.network.pois:
            p_x = [p.pos[0] for p in self.network.pois]
            p_y = [p.pos[1] for p in self.network.pois]
            poi_colors = ['lime' if p.is_covered else 'red' for p in self.network.pois]
            self.poi_nodes_plot = self.ax.scatter(p_x, p_y, s=60, marker='X', c=poi_colors, edgecolors='black', zorder=4)
        else:
            self.poi_nodes_plot = self.ax.scatter([], [], s=60, marker='X', visible=False, zorder=4)

        plt.show(block=False)
        plt.pause(0.1)

        if self.network.sink_node:
            sink_x, sink_y = self.network.sink_node.pos
            self.sink_marker_plot = self.ax.scatter([sink_x], [sink_y], s=100, c='purple', edgecolors='black', marker='s', zorder=5, label='Base Station')
        else:
            self.sink_marker_plot = self.ax.scatter([], [], s=100, marker='s', visible=False, zorder=5, label='Base Station')

    def update_plot(self, current_round):
        """
        Aktualizuje wykres wizualizacji na podstawie bieżącego stanu sieci.

        Odświeża pozycje (jeśli sensory się poruszają, co nie dotyczy obecnego modelu),
        stany (kolory), zasięgi sensorów oraz potencjalne połączenia komunikacyjne.
        Metoda jest wywoływana przez SimulationManager po każdej rundzie (lub co plot_interval rund).

        Args:
            current_round (int): Numer bieżącej rundy symulacji.

        Returns:
            bool: True, jeśli okno wizualizacji jest nadal otwarte i powinno być
                  aktualizowane; False, jeśli okno zostało zamknięte.
        """
        if not self.is_window_open:
            return False
            
        if current_round % self.plot_interval != 0 and current_round > 0:
            return True

        # --- Kolory sensorów ---
        colors = []
        edge_colors = []
        for s_id, s_obj in self.network.sensors.items():
            if s_obj.is_sink:
                colors.append('purple')
                edge_colors.append('black')
            elif s_obj.state == SensorState.DEAD or s_obj.is_failed:
                colors.append('black')
                edge_colors.append('grey')
            elif s_obj.state == SensorState.ACTIVE:
                colors.append('green')
                edge_colors.append('darkgreen')
            elif s_obj.state == SensorState.SLEEP:
                colors.append('grey')
                edge_colors.append('dimgrey')
            else:
                colors.append('blue') # Domyślny, na wszelki wypadek
                edge_colors.append('darkblue')

        positions = [s.pos for s in self.network.sensors.values()]
        self.sensor_nodes_plot.set_offsets(positions)
        self.sensor_nodes_plot.set_color(colors)
        self.sensor_nodes_plot.set_edgecolor(edge_colors)

        # --- Zasięgi ---
        for circle in self.comm_range_circles + self.sensing_range_circles:
            circle.remove()
        self.comm_range_circles.clear()
        self.sensing_range_circles.clear()

        show_ranges = self.network.config.getboolean("Visualization", "show_ranges", fallback=False) if hasattr(self.network, 'config') else False

        if show_ranges:
            for s in self.network.sensors.values():
                if s.state == SensorState.ACTIVE:
                    sens_circle = plt.Circle(s.pos, s.sensing_range, color='orange', alpha=0.1, fill=True, zorder=1)
                    self.ax.add_artist(sens_circle)
                    self.sensing_range_circles.append(sens_circle)

        # --- Kolory POI (pokryte/niepokryte) ---
        if self.network.pois and self.poi_nodes_plot:
            poi_positions = [p.pos for p in self.network.pois]
            poi_colors = ['lime' if p.is_covered else 'red' for p in self.network.pois]
            self.poi_nodes_plot.set_offsets(poi_positions)
            self.poi_nodes_plot.set_color(poi_colors)
            self.poi_nodes_plot.set_visible(True)
            for poi, color in zip(self.network.pois, poi_colors):
                logging.info(f"POI {poi.id}: Visible: {self.poi_nodes_plot.get_visible()}, Color: {color}")
        elif self.poi_nodes_plot:
            self.poi_nodes_plot.set_visible(False)

        if self.network.sink_node and self.sink_marker_plot:
            self.sink_marker_plot.set_offsets([self.network.sink_node.pos])
            self.sink_marker_plot.set_visible(True)
        elif self.sink_marker_plot:
            self.sink_marker_plot.set_visible(False)

        # --- Ścieżki komunikacji (do bazy) ---
        for line in self.comm_links_plot:
            line.pop(0).remove() # Usuń stary obiekt linii
        self.comm_links_plot.clear()

        show_paths = self.network.config.getboolean("Visualization", "show_paths", fallback=True) if hasattr(self.network, 'config') else True
        if show_paths:
            for s_id, sensor in self.network.sensors.items():
                # Wizualizacja ścieżek z buforów pakietów
                for packet in sensor.data_buffer:
                    if packet.next_hop_id:
                        receiver = self.network.get_sensor(packet.next_hop_id)
                        if receiver:
                            line = self.ax.plot([sensor.pos[0], receiver.pos[0]],
                                                [sensor.pos[1], receiver.pos[1]],
                                                'b--', alpha=0.3, linewidth=0.8, zorder=0)
                            self.comm_links_plot.append(line)
                # Wizualizacja wybranej ścieżki do sinka (jeśli sensor.parent_to_sink jest ustawiony)
                if sensor.parent_to_sink and sensor.state == SensorState.ACTIVE:
                    parent = self.network.get_sensor(sensor.parent_to_sink)
                    if parent:
                        line = self.ax.plot([sensor.pos[0], parent.pos[0]],
                                            [sensor.pos[1], parent.pos[1]],
                                            'r-', alpha=0.5, linewidth=1, zorder=0)
                        self.comm_links_plot.append(line)


        self.round_text.set_text(f'Round: {current_round}')
        self.fig.canvas.draw_idle()
        plt.pause(0.01) # Krótka pauza, aby GUI mogło się odświeżyć
        return True

    def close_plot(self):
        """
        Obsługuje zdarzenie zamknięcia okna wykresu Matplotlib.

        Ustawia flagę `is_running` na False, co sygnalizuje SimulationManagerowi
        o potrzebie zatrzymania aktualizacji wizualizacji i ewentualnie całej symulacji.

        Args:
            event (CloseEvent): Zdarzenie zamknięcia okna.
        """
        if self.is_window_open:
            plt.close(self.fig)
            self.is_window_open = False