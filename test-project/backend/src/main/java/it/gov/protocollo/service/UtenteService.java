package it.gov.protocollo.service;

import it.gov.protocollo.entity.Utente;
import it.gov.protocollo.entity.RuoloUtente;
import it.gov.protocollo.repository.UtenteRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

/**
 * Service per la gestione degli utenti della PA.
 * Contiene la logica di business per CRUD e validazioni.
 */
@Service
@Transactional
public class UtenteService {

    private final UtenteRepository utenteRepository;

    public UtenteService(UtenteRepository utenteRepository) {
        this.utenteRepository = utenteRepository;
    }

    /**
     * Recupera tutti gli utenti attivi.
     */
    @Transactional(readOnly = true)
    public List<Utente> findAllAttivi() {
        return utenteRepository.findByAttivoTrue();
    }

    /**
     * Recupera un utente per ID.
     */
    @Transactional(readOnly = true)
    public Optional<Utente> findById(Long id) {
        return utenteRepository.findById(id);
    }

    /**
     * Cerca utente per codice fiscale.
     */
    @Transactional(readOnly = true)
    public Optional<Utente> findByCodiceFiscale(String codiceFiscale) {
        return utenteRepository.findByCodiceFiscale(codiceFiscale.toUpperCase());
    }

    /**
     * Crea un nuovo utente previa validazione del codice fiscale.
     */
    public Utente creaUtente(Utente utente) {
        // Verifica unicità codice fiscale
        if (utenteRepository.findByCodiceFiscale(utente.getCodiceFiscale()).isPresent()) {
            throw new IllegalArgumentException(
                "Utente con codice fiscale " + utente.getCodiceFiscale() + " già esistente"
            );
        }
        return utenteRepository.save(utente);
    }

    /**
     * Aggiorna i dati di un utente esistente.
     */
    public Utente aggiornaUtente(Long id, Utente datiAggiornati) {
        Utente esistente = utenteRepository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Utente non trovato: " + id));

        esistente.setNome(datiAggiornati.getNome());
        esistente.setCognome(datiAggiornati.getCognome());
        esistente.setEmail(datiAggiornati.getEmail());
        esistente.setRuolo(datiAggiornati.getRuolo());
        esistente.setEnteAppartenenza(datiAggiornati.getEnteAppartenenza());

        return utenteRepository.save(esistente);
    }

    /**
     * Disattiva un utente (soft delete).
     */
    public void disattivaUtente(Long id) {
        Utente utente = utenteRepository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Utente non trovato: " + id));
        utente.setAttivo(false);
        utenteRepository.save(utente);
    }

    /**
     * Registra l'ultimo accesso dell'utente.
     */
    public void registraAccesso(Long id) {
        utenteRepository.findById(id).ifPresent(utente -> {
            utente.setUltimoAccesso(LocalDateTime.now());
            utenteRepository.save(utente);
        });
    }

    /**
     * Cerca utenti per ente di appartenenza.
     */
    @Transactional(readOnly = true)
    public List<Utente> findByEnte(String ente) {
        return utenteRepository.findByEnteAppartenenzaContainingIgnoreCase(ente);
    }
}
