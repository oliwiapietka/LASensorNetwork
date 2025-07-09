# utils/logger.py
"""
Moduł odpowiedzialny za zarządzanie logowaniem wyników symulacji do pliku.

Definiuje klasę SimulationLogger, która umożliwia zapisywanie komunikatów
ogólnych oraz szczegółowych statystyk z każdej rundy symulacji do
określonego pliku wyjściowego.
"""
import json
import os

class SimulationLogger:
    """
    Klasa do logowania przebiegu i wyników symulacji do pliku.

    Umożliwia zapisywanie różnego rodzaju informacji, w tym komunikatów
    tekstowych i zserializowanych statystyk z kolejnych rund symulacji.
    """
    def __init__(self, filepath="results/simulation_log.txt"):
        """
        Konstruktor klasy SimulationLogger.

        Otwiera plik do zapisu logów. Tworzy katalog docelowy, jeśli nie istnieje.

        Args:
            filepath (str): Pełna ścieżka do pliku, w którym mają być zapisywane logi symulacji.
        """
        self.filepath = filepath
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        # Otwieramy plik w trybie 'w' na początku, aby go wyczyścić/utworzyć
        with open(self.filepath, 'w') as f:
            f.write("Simulation Log\n") # Nagłówek lub pusty plik
        self.log_buffer = [] # Bufor na wpisy, żeby nie pisać do pliku co chwilę

    def log_round_stats(self, stats_dict):
        """
        Zapisuje ogólny komunikat tekstowy do pliku logu.

        Args:
            message (str): Komunikat tekstowy do zapisania.
        """
        self.log_buffer.append(json.dumps(stats_dict))
        if len(self.log_buffer) >= 10: # Zapisuj co 10 wpisów
            self._flush_buffer()

    def _flush_buffer(self):
        """
        Zapisuje statystyki z pojedynczej rundy symulacji.

        Statystyki są zapisywane w formacie, który można później łatwo przetworzyć,
        np. jako linia JSON dla każdej rundy.

        Args:
            stats (dict): Słownik zawierający statystyki dla bieżącej rundy.
        """
        if not self.log_buffer:
            return
        with open(self.filepath, 'a') as f:
            for entry in self.log_buffer:
                f.write(entry + "\n")
        self.log_buffer = []

    def log_message(self, message):
        """
        Zapisuje ogólny komunikat tekstowy do pliku logu.

        Args:
            message (str): Komunikat tekstowy do zapisania.
        """
        with open(self.filepath, 'a') as f:
            f.write(f"MSG: {message}\n")

    def close(self):
        """
        Zamyka plik logu.

        Powinna być wywołana na końcu symulacji, aby upewnić się, że wszystkie
        dane zostały zapisane i zasoby pliku zostały zwolnione.
        """
        self._flush_buffer() # Upewnij się, że wszystko jest zapisane
        print(f"Simulation log saved to {self.filepath}")