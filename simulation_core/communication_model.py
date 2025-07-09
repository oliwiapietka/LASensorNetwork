# simulation_core/communication_model.py
"""
Moduł definiujący model komunikacji bezprzewodowej w sieci sensorowej.

Zawiera definicję struktury pakietu danych (`Packet`) oraz klasę
`CommunicationManager` odpowiedzialną za symulowanie procesów transmisji,
odbioru, utraty pakietów i zarządzanie buforami komunikacyjnymi sensorów.
Model uwzględnia zużycie energii sensorów podczas komunikacji
zgodnie z modelem energetycznym (`EnergyConsumption`).
"""

import random
from .energy_model import EnergyConsumption
import logging
from .sensor import SensorState

class Packet:    
    """
    Reprezentuje pojedynczy pakiet danych przesyłany w sieci sensorowej.

    Pakiet zawiera informacje o nadawcy (źródle), odbiorcy (celu),
    typie danych, ładunku (payload), ścieżce, którą przebył, oraz
    podstawowe metadane, takie jak ID i opóźnienie.
    """
    def __init__(self, source_id, destination_id, data_type, payload, path_taken=None):
        """
        Konstruktor klasy Packet.

        Inicjalizuje pakiet danych z podanymi informacjami.

        Args:
            source_id (int): ID sensora, który wygenerował pakiet (oryginalne źródło).
            destination_id (int): ID docelowego sensora (np. stacja bazowa).
            data_type (str): Typ danych przenoszonych przez pakiet (np. "POI_REPORT", "STATUS").
            payload (any): Rzeczywista treść/ładunek pakietu (może być słownik, string itp.).
            path_taken (list[int] | None): Opcjonalna lista ID sensorów, przez które pakiet
                                          już przeszedł. Domyślnie zawiera tylko źródło.
        """
        self.source_id = source_id
        self.destination_id = destination_id
        self.current_hop_id = source_id
        self.next_hop_id = None
        self.data_type = data_type
        self.payload = payload
        self.path_taken = path_taken if path_taken is not None else [source_id]
        self.id = random.randint(10000, 99999)
        self.latency = 0
        self.creation_time = 0

    def __repr__(self):
        """
        Zwraca reprezentację obiektu Packet jako string (do celów debugowania/logowania).
        """
        return (f"Packet(id={self.id}, from={self.source_id} to={self.destination_id}, "
                f"type={self.data_type}, cur={self.current_hop_id}, next={self.next_hop_id})")

class CommunicationManager:
    """
    Zarządza procesami komunikacji między sensorami w sieci.

    Odpowiada za symulowanie wysyłania pojedynczych pakietów (unicast)
    i wiadomości broadcastowych, uwzględniając utratę pakietów, zasięg
    komunikacji, stan energetyczny sensorów oraz opóźnienia transmisji.
    Komunikuje się z obiektami Sensor i Network w celu aktualizacji
    stanów, energii i buforów danych.
    """
    def __init__(self, network_ref, packet_loss_probability=0.01, transmission_delay_per_hop=0.1):
        """
        Konstruktor klasy CommunicationManager.

        Inicjalizuje menedżer komunikacji z referencją do sieci,
        prawdopodobieństwem utraty pakietu i opóźnieniem transmisji na hop.

        Args:
            network_ref ('Network'): Referencja do obiektu Network, którą menedżer
                                    wykorzystuje do dostępu do sensorów i ich stanów.
                                    Użyj string type hint, aby uniknąć cyklicznego importu.
            packet_loss_probability (float): Prawdopodobieństwo, że pojedynczy pakiet
                                             zostanie utracony podczas transmisji (domyślnie 0.01).
                                             Wartość z zakresu [0.0, 1.0].
            transmission_delay_per_hop (float): Opóźnienie dodawane do opóźnienia pakietu
                                                przy każdym przeskok na kolejny węzeł (domyślnie 0.1).
                                                Jednostki powinny być spójne z jednostkami czasu symulacji (rundy).
        """
        self.network = network_ref
        self.packet_loss_probability = packet_loss_probability
        self.transmission_delay_per_hop = transmission_delay_per_hop

    def send_packet(self, sender_id: int, packet: 'Packet', receiver_id: int) -> tuple[bool, str]:
        """
        Symuluje próbę wysłania pojedynczego pakietu danych od sensora `sender_id`
        do sensora `receiver_id`.

        Jest to operacja unicast do następnego skoku, a nie do ostatecznego celu pakietu.
        Metoda sprawdza warunki konieczne do udanej transmisji (stan sensorów, zasięg),
        symuluje utratę pakietu i zużycie energii, a w przypadku sukcesu dodaje pakiet
        do bufora odbiorczego sensora odbiorcy (jeśli żyje i może odbierać).

        Args:
            sender_id (int): ID sensora, który próbuje wysłać pakiet.
            packet ('Packet'): Obiekt pakietu do wysłania.
            receiver_id (int): ID sensora, który jest bezpośrednim odbiorcą (następny skok).

        Returns:
            tuple[bool, str]: Para (success, status_message).
                              success (bool) jest True, jeśli pakiet został
                              pomyślnie przekazany do CommunicationManager (niekoniecznie odebrany).
                              status_message (str) zawiera opis wyniku operacji.
        """
        sender = self.network.get_sensor(sender_id)
        receiver = self.network.get_sensor(receiver_id)

        # Sprawdzenia Nadawcy
        if not sender:
            return False, f"SENDER_NOT_FOUND (ID: {sender_id})"
        if sender.is_failed:
            return False, f"SENDER_FAILED (ID: {sender_id})"
        if sender.state == SensorState.DEAD:
            return False, f"SENDER_DEAD (ID: {sender_id})"
        if sender.state == SensorState.SLEEP:
            return False, f"SENDER_ASLEEP (ID: {sender_id})"
        # Domyślnie, jeśli nie jest FAILED, DEAD, SLEEP, to jest ACTIVE (lub sink)

        # Sprawdzenia Odbiorcy
        if not receiver:
            # Nadawca próbował wysłać, więc ponosi koszt (jeśli żyje i jest aktywny)
            sender.update_energy(amount=EnergyConsumption.communication_tx_cost(0)) # Minimalny koszt próby
            return False, f"RECEIVER_NOT_FOUND (ID: {receiver_id})"
        if receiver.is_failed:
            sender.update_energy(amount=EnergyConsumption.communication_tx_cost(0))
            return False, f"RECEIVER_FAILED (ID: {receiver_id})"
        if receiver.state == SensorState.DEAD:
            sender.update_energy(amount=EnergyConsumption.communication_tx_cost(0))
            return False, f"RECEIVER_DEAD (ID: {receiver_id})"
        if receiver.state == SensorState.SLEEP:
            sender.update_energy(amount=EnergyConsumption.communication_tx_cost(0))
            return False, f"RECEIVER_ASLEEP (ID: {receiver_id})" # Nie można wysłać do uśpionego

        # Sprawdzenie Zasięgu
        distance = sender.distance_to(receiver.pos)
        if distance > sender.comm_range:
            return False, f"OUT_OF_RANGE (Sender: {sender_id} -> Receiver: {receiver_id}, Dist: {distance:.2f}, Range: {sender.comm_range})"

        # Koszty Energii i Symulacja Utraty
        tx_cost = EnergyConsumption.communication_tx_cost(distance)
        sender.update_energy(amount=tx_cost) # Metoda update_energy obsłuży ewentualną śmierć nadawcy

        if sender.state == SensorState.DEAD: # Nadawca mógł umrzeć podczas wysyłania
            return False, f"SENDER_DIED_DURING_TX (ID: {sender_id})"

        if random.random() < self.packet_loss_probability:
            # Pakiet utracony, ale energia za wysłanie została zużyta
            return False, f"PACKET_LOST_IN_TRANSIT (Sender: {sender_id} -> Receiver: {receiver_id})"

        rx_cost = EnergyConsumption.communication_rx_cost()
        receiver.update_energy(amount=rx_cost) # Odbiorca zużywa energię na odbiór
        
        # Aktualizacja Pakietu i Dostarczenie
        packet.current_hop_id = receiver_id # Obecnym "posiadaczem" pakietu jest receiver_id
        
        # Aktualizacja ścieżki - dodajemy węzły, przez które pakiet rzeczywiście przeszedł
        if not packet.path_taken or packet.path_taken[-1] != sender_id : # Jeśli ścieżka jest pusta lub ostatni to nie obecny sender
             if not packet.path_taken and packet.source_id == sender_id: # Pierwszy skok
                  packet.path_taken = [sender_id]
             elif packet.path_taken and packet.path_taken[-1] != sender_id :
                  packet.path_taken.append(sender_id)


        if packet.path_taken[-1] != receiver_id: # Unikaj duplikatów odbiorcy w ścieżce
            packet.path_taken.append(receiver_id)

        packet.latency += self.transmission_delay_per_hop

        if receiver.state != SensorState.DEAD and not receiver.is_failed: # Dodaj do bufora tylko jeśli odbiorca żyje
            receiver.data_buffer.append(packet)
            return True, f"DELIVERED_TO_RECEIVER_BUFFER (ID: {receiver_id})"
        else:
            return False, f"RECEIVER_DIED_OR_FAILED_UPON_RX (ID: {receiver_id})"


    def broadcast_message(self, sender_id: int, message_type: str, payload: any, max_hops=1) -> int:
        """
        Symuluje wysłanie wiadomości broadcastowej od sensora `sender_id`
        do jego bezpośrednich sąsiadów.

        Wiadomość broadcastowa dociera do wszystkich aktywnych, nieuszkodzonych
        i nie martwych sąsiadów nadawcy, którzy są w stanie odebrać broadcast.
        Uwzględnia utratę pakietu i zużycie energii na nadawanie i odbiór.
        Metoda `handle_broadcast_message` na obiekcie odbiorcy jest wywoływana
        dla każdego pomyślnie odebranego broadcastu.

        Args:
            sender_id (int): ID sensora, który wysyła broadcast.
            message_type (str): Typ wiadomości broadcastowej.
            payload (any): Treść wiadomości broadcastowej.
            max_hops (int): Maksymalna liczba przeskoków broadcastu. W tej implementacji
                            domyślnie 1, co oznacza tylko do bezpośrednich sąsiadów.
                            (Implementacja wielohopowego broadcastu byłaby bardziej złożona).

        Returns:
            int: Liczba sąsiadów, którzy pomyślnie odebrali wiadomość broadcastową.
        """
        sender = self.network.get_sensor(sender_id)

        # Sprawdzenia Nadawcy Broadcastu
        if not sender: return 0
        if sender.is_failed: return 0
        if sender.state == SensorState.DEAD: return 0
        if sender.state == SensorState.SLEEP: return 0 # Uśpione sensory nie wysyłają broadcastów

        broadcast_tx_cost = EnergyConsumption.communication_tx_cost(sender.comm_range / 2) # Uśredniony koszt
        sender.update_energy(amount=broadcast_tx_cost)
        
        if sender.state == SensorState.DEAD: # Umarł podczas próby wysłania broadcastu
            return 0

        successful_sends = 0
        for neighbor_obj in sender.neighbors: # sender.neighbors to lista obiektów Sensor
            # Sprawdzenia Odbiorcy Broadcastu
            if neighbor_obj.is_failed: continue
            if neighbor_obj.state == SensorState.DEAD: continue
            if neighbor_obj.state == SensorState.SLEEP: continue # Uśpione sensory nie odbierają broadcastów
            
            # Symulacja utraty pakietu dla każdego odbiorcy indywidualnie
            if random.random() < self.packet_loss_probability:
                continue

            rx_cost = EnergyConsumption.communication_rx_cost()
            neighbor_obj.update_energy(amount=rx_cost)
            
            if neighbor_obj.state == SensorState.DEAD: # Umarł po odebraniu broadcastu
                continue 

            # Wywołanie metody w obiekcie sąsiada do obsłużenia wiadomości
            if hasattr(neighbor_obj, 'handle_broadcast_message'):
                neighbor_obj.handle_broadcast_message(
                    sender_id=sender.id,
                    message_type=message_type,
                    payload=payload,
                    network_time=self.network.current_round
                )
            successful_sends += 1
        return successful_sends