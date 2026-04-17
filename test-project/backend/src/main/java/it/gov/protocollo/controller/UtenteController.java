package it.gov.protocollo.controller;

import it.gov.protocollo.entity.Utente;
import it.gov.protocollo.service.UtenteService;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import jakarta.validation.Valid;
import java.util.List;

/**
 * Controller REST per la gestione degli utenti.
 * Espone le API CRUD per il frontend Angular.
 */
@RestController
@RequestMapping("/api/utenti")
public class UtenteController {

    private final UtenteService utenteService;

    public UtenteController(UtenteService utenteService) {
        this.utenteService = utenteService;
    }

    /**
     * GET /api/utenti — Lista tutti gli utenti attivi.
     */
    @GetMapping("")
    public ResponseEntity<List<Utente>> getAll() {
        return ResponseEntity.ok(utenteService.findAllAttivi());
    }

    /**
     * GET /api/utenti/{id} — Dettaglio utente per ID.
     */
    @GetMapping("/{id}")
    public ResponseEntity<Utente> getById(@PathVariable Long id) {
        return utenteService.findById(id)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }

    /**
     * GET /api/utenti/cf/{codiceFiscale} — Cerca utente per codice fiscale.
     */
    @GetMapping("/cf/{codiceFiscale}")
    public ResponseEntity<Utente> getByCodiceFiscale(@PathVariable String codiceFiscale) {
        return utenteService.findByCodiceFiscale(codiceFiscale)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }

    /**
     * POST /api/utenti — Crea un nuovo utente.
     */
    @PostMapping("")
    public ResponseEntity<Utente> create(@Valid @RequestBody Utente utente) {
        Utente creato = utenteService.creaUtente(utente);
        return ResponseEntity.status(HttpStatus.CREATED).body(creato);
    }

    /**
     * PUT /api/utenti/{id} — Aggiorna un utente esistente.
     */
    @PutMapping("/{id}")
    public ResponseEntity<Utente> update(@PathVariable Long id, @Valid @RequestBody Utente utente) {
        Utente aggiornato = utenteService.aggiornaUtente(id, utente);
        return ResponseEntity.ok(aggiornato);
    }

    /**
     * DELETE /api/utenti/{id} — Disattiva un utente (soft delete).
     */
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        utenteService.disattivaUtente(id);
        return ResponseEntity.noContent().build();
    }

    /**
     * GET /api/utenti/ente/{ente} — Cerca utenti per ente di appartenenza.
     */
    @GetMapping("/ente/{ente}")
    public ResponseEntity<List<Utente>> getByEnte(@PathVariable String ente) {
        return ResponseEntity.ok(utenteService.findByEnte(ente));
    }
}
