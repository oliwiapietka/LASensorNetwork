 # simulation_core/energy_model.py
"""
Moduł definiujący stałe kosztów energetycznych sensorów w różnych stanach
i podczas operacji komunikacyjnych.

Modeluje zużycie energii w stanach uśpienia (SLEEP), monitorowania (ACTIVE),
przetwarzania oraz podczas transmisji i odbioru pakietów.
"""

class EnergyConsumption:
    """
    Stałe reprezentujące koszty energetyczne sensorów.
    """
    SLEEP = 0.001           # Energia w stanie uśpienia (na jednostkę czasu)
    MONITORING = 0.05       # Energia na monitorowanie (nasłuch, praca sensora)
    PROCESSING = 0.02       # Energia na przetwarzanie danych (np. przez LA/CA)

    # Parametry modelu energetycznego komunikacji (model radiowy)
    E_ELEC = 50e-9           # Energia na elektronikę nadajnika/odbiornika (na bit)
    E_AMP = 100e-12         # Energia wzmacniacza nadajnika (na bit na m^2/m^4)

    PATH_LOSS_EXPONENT = 2
    PACKET_SIZE_BITS = 512  # Przykładowy rozmiar pakietu w bitach

    @staticmethod
    def communication_tx_cost(distance):
        """
        Oblicza koszt energetyczny transmisji jednego pakietu danych na daną odległość.

        Model bazuje na sumie energii zużytej przez elektronikę nadajnika
        i energię zużytą przez wzmacniacz, która zależy od odległości
        i wykładnika tłumienia ścieżki.

        Args:
            distance (float): Odległość między nadajnikiem a odbiornikiem.

        Returns:
            float: Koszt energetyczny (np. w Dżulach) transmisji pakietu.
        """
        if distance == 0:
            return EnergyConsumption.E_ELEC * EnergyConsumption.PACKET_SIZE_BITS
        cost = (EnergyConsumption.E_ELEC * EnergyConsumption.PACKET_SIZE_BITS +
                EnergyConsumption.E_AMP * EnergyConsumption.PACKET_SIZE_BITS * (distance ** EnergyConsumption.PATH_LOSS_EXPONENT))
        return cost

    @staticmethod
    def communication_rx_cost():
        """
        Oblicza koszt energetyczny odbioru jednego pakietu danych.

        W tym uproszczonym modelu, koszt odbioru zależy głównie od energii
        zużytej przez elektronikę odbiornika i nie zależy od odległości.

        Returns:
            float: Koszt energetyczny (np. w Dżulach) odbioru pakietu.
        """
        return EnergyConsumption.E_ELEC * EnergyConsumption.PACKET_SIZE_BITS