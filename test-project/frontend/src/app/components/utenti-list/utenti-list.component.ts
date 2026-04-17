import { Component, OnInit } from '@angular/core';
import { UtenteService } from '../../services/utente.service';

export interface Utente {
  id: number;
  codiceFiscale: string;
  nome: string;
  cognome: string;
  email: string;
  ruolo: string;
  enteAppartenenza: string;
  attivo: boolean;
}

@Component({
  selector: 'app-utenti-list',
  templateUrl: './utenti-list.component.html',
  styleUrls: ['./utenti-list.component.scss']
})
export class UtentiListComponent implements OnInit {
  utenti: Utente[] = [];
  loading = true;
  errorMessage = '';
  searchTerm = '';

  constructor(private utenteService: UtenteService) {}

  ngOnInit(): void {
    this.loadUtenti();
  }

  loadUtenti(): void {
    this.loading = true;
    this.utenteService.getAll().subscribe({
      next: (data) => {
        this.utenti = data;
        this.loading = false;
      },
      error: (err) => {
        this.errorMessage = 'Errore nel caricamento degli utenti';
        this.loading = false;
      }
    });
  }

  onSearch(): void {
    if (this.searchTerm.trim()) {
      this.utenteService.searchByEnte(this.searchTerm).subscribe({
        next: (data) => this.utenti = data,
        error: () => this.errorMessage = 'Errore nella ricerca'
      });
    } else {
      this.loadUtenti();
    }
  }

  deleteUtente(id: number): void {
    if (confirm('Confermi la disattivazione dell\'utente?')) {
      this.utenteService.delete(id).subscribe({
        next: () => this.loadUtenti(),
        error: () => this.errorMessage = 'Errore nella disattivazione'
      });
    }
  }
}
