package it.gov.protocollo.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;

/**
 * Entità Utente — rappresenta un utente del sistema PA.
 */
@Entity
@Table(name = "utenti")
public class Utente {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "codice_fiscale", nullable = false, unique = true, length = 16)
    private String codiceFiscale;

    @Column(nullable = false, length = 100)
    private String nome;

    @Column(nullable = false, length = 100)
    private String cognome;

    @Column(nullable = false, unique = true)
    private String email;

    @Column(name = "ruolo", nullable = false, length = 50)
    @Enumerated(EnumType.STRING)
    private RuoloUtente ruolo;

    @Column(name = "ente_appartenenza", length = 200)
    private String enteAppartenenza;

    @Column(name = "data_creazione", nullable = false)
    private LocalDateTime dataCreazione;

    @Column(name = "ultimo_accesso")
    private LocalDateTime ultimoAccesso;

    @Column(nullable = false)
    private Boolean attivo = true;

    @PrePersist
    protected void onCreate() {
        dataCreazione = LocalDateTime.now();
    }

    // Getter e Setter
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    public String getCodiceFiscale() { return codiceFiscale; }
    public void setCodiceFiscale(String codiceFiscale) { this.codiceFiscale = codiceFiscale; }

    public String getNome() { return nome; }
    public void setNome(String nome) { this.nome = nome; }

    public String getCognome() { return cognome; }
    public void setCognome(String cognome) { this.cognome = cognome; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public RuoloUtente getRuolo() { return ruolo; }
    public void setRuolo(RuoloUtente ruolo) { this.ruolo = ruolo; }

    public String getEnteAppartenenza() { return enteAppartenenza; }
    public void setEnteAppartenenza(String enteAppartenenza) { this.enteAppartenenza = enteAppartenenza; }

    public LocalDateTime getDataCreazione() { return dataCreazione; }
    public LocalDateTime getUltimoAccesso() { return ultimoAccesso; }
    public void setUltimoAccesso(LocalDateTime ultimoAccesso) { this.ultimoAccesso = ultimoAccesso; }

    public Boolean getAttivo() { return attivo; }
    public void setAttivo(Boolean attivo) { this.attivo = attivo; }
}
