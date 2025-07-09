# visualization/plot_generator.py
"""
Moduł odpowiedzialny za generowanie wykresów statystyk symulacji po jej zakończeniu.

Analizuje zebrane dane statystyczne z każdej rundy i tworzy wykresy
pokazujące trendy metryk takich jak średnia energia, pokrycie POI, PDR,
opóźnienie, stany sensorów, prawdopodobieństwa LA itp. Wykresy są zapisywane
do pliku.
"""
import logging
logging.getLogger('matplotlib').setLevel(logging.WARNING)
import matplotlib.pyplot as plt
import os
import pandas as pd
import matplotlib
matplotlib.use('Agg')

class PlotGenerator:
    """
    Klasa do generowania wykresów podsumowujących wyniki symulacji.

    Przyjmuje listę zebranych statystyk z każdej rundy i generuje serię
    standardowych wykresów obrazujących kluczowe metryki przebiegu symulacji
    w czasie.
    """
    def __init__(self, all_stats_list, output_directory="results/"):
        """
        Konstruktor klasy PlotGenerator.

        Inicjalizuje generator wykresów z zebranymi danymi statystycznymi
        i ścieżką katalogu docelowego do zapisu wykresów.

        Args:
            all_stats (list[dict]): Lista słowników, gdzie każdy słownik
                                    zawiera statystyki z jednej rundy symulacji.
                                    Lista powinna być posortowana według numeru rundy.
            output_dir (str): Ścieżka do katalogu, w którym zostaną zapisane wygenerowane wykresy.
                              Katalog zostanie utworzony, jeśli nie istnieje.
        """
        self.stats_df = pd.DataFrame(all_stats_list) # Konwersja listy słowników do DataFrame
        self.output_dir = output_directory
        os.makedirs(self.output_dir, exist_ok=True)

    def plot_sensor_counts(self):
        """
        Generuje wykres liniowy pokazujący liczbę sensorów w poszczególnych
        stanach (Active, Sleep, Dead/Failed) w funkcji rundy symulacji.

        Wykres jest zapisywany do pliku "sensor_counts.png" w katalogu wyjściowym.
        """
        if 'round' not in self.stats_df.columns: return
        plt.figure(figsize=(10, 6))
        plt.plot(self.stats_df['round'], self.stats_df['active_sensors'], label='Active Sensors', color='green')
        plt.plot(self.stats_df['round'], self.stats_df['sleep_sensors'], label='Sleep Sensors', color='grey')
        plt.plot(self.stats_df['round'], self.stats_df['dead_sensors'], label='Dead/Failed Sensors', color='black')
        plt.xlabel("Round")
        plt.ylabel("Number of Sensors")
        plt.title("Sensor States Over Time")
        plt.legend()
        plt.grid(True)
        plt.savefig(os.path.join(self.output_dir, "sensor_counts.png"))
        plt.close()

    def plot_average_energy(self):
        """
        Generuje wykres liniowy pokazujący średni poziom energii pozostałej
        w żywych sensorach (niebędących stacją bazową) w funkcji rundy symulacji.

        Wykres jest zapisywany do pliku "average_energy.png".
        """
        if 'round' not in self.stats_df.columns or 'avg_energy_alive_non_sink' not in self.stats_df.columns:
            print("Missing 'avg_energy_alive' column in stats data. Skipping average energy plot.")
            return
        plt.figure(figsize=(10, 6))
        plt.plot(self.stats_df['round'], self.stats_df['avg_energy_alive_non_sink'], label='Average Energy (Alive Sensors)', color='blue')
        plt.xlabel("Round")
        plt.ylabel("Average Energy")
        plt.title("Average Network Energy Over Time")
        plt.legend()
        plt.grid(True)
        plt.savefig(os.path.join(self.output_dir, "average_energy.png"))
        plt.close()

    def plot_coverage_q(self):
        """
        Generuje wykres liniowy pokazujący wskaźnik Q-pokrycia sieci
        w funkcji rundy symulacji.

        Wykres jest zapisywany do pliku "coverage_q.png".
        """

        if 'round' not in self.stats_df.columns or 'coverage_q_k' not in self.stats_df.columns:
            print("Missing 'coverage_q' column in stats data. Skipping coverage plot.")
            return
        plt.figure(figsize=(10, 6))
        plt.plot(self.stats_df['round'], self.stats_df['coverage_q_k'], label='Coverage (Q)', color='red')
        plt.xlabel("Round")
        plt.ylabel("Coverage (Q)")
        plt.title("POI Coverage Over Time")
        plt.ylim(0, 1.1) # Q jest między 0 a 1
        plt.legend()
        plt.grid(True)
        plt.savefig(os.path.join(self.output_dir, "coverage_q.png"))
        plt.close()

    def plot_pdr(self):
        """
        Generuje wykres liniowy pokazujący Packet Delivery Ratio (PDR)
        (stosunek pakietów dostarczonych do sinka do wygenerowanych)
        w funkcji rundy symulacji.

        Wykres jest zapisywany do pliku "pdr.png".
        """
        if 'round' not in self.stats_df.columns or 'pdr' not in self.stats_df.columns: return
        plt.figure(figsize=(10, 6))
        plt.plot(self.stats_df['round'], self.stats_df['pdr'], label='Packet Delivery Ratio (PDR)', color='orange')
        plt.xlabel("Round")
        plt.ylabel("PDR")
        plt.title("Packet Delivery Ratio Over Time")
        plt.ylim(0, 1.1)
        plt.legend()
        plt.grid(True)
        plt.savefig(os.path.join(self.output_dir, "pdr.png"))
        plt.close()

    def plot_latency(self):
        """
        Generuje wykres liniowy pokazujący średnie opóźnienie pakietów
        dostarczonych do stacji bazowej (sink) w funkcji rundy symulacji.

        Wykres jest rysowany tylko dla rund, w których dostarczono co najmniej
        jeden pakiet (średnie opóźnienie > 0).
        Wykres jest zapisywany do pliku "latency.png".
        """
        if 'round' not in self.stats_df.columns or 'avg_latency' not in self.stats_df.columns: return
        valid_latency_df = self.stats_df[self.stats_df['avg_latency'] > 0]
        if not valid_latency_df.empty:
            plt.figure(figsize=(10, 6))
            plt.plot(valid_latency_df['round'], valid_latency_df['avg_latency'], label='Average Latency', color='purple')
            plt.xlabel("Round")
            plt.ylabel("Latency (rounds/time units)")
            plt.title("Average Packet Latency Over Time (for delivered packets)")
            plt.legend()
            plt.grid(True)
            plt.savefig(os.path.join(self.output_dir, "latency.png"))
            plt.close()
        else:
            print("No latency data to plot (all avg_latency values are zero or missing).")

    def plot_all(self):
        """
        Generuje wszystkie standardowe wykresy podsumowujące wyniki symulacji.

        Wywołuje poszczególne metody generujące konkretne typy wykresów
        zdefiniowane w tej klasie.
        """
        self.plot_sensor_counts()
        self.plot_average_energy()
        self.plot_coverage_q()
        self.plot_pdr()
        self.plot_latency()
        print(f"All plots saved to {self.output_dir}")