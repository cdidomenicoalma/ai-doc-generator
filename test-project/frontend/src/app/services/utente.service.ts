import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

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

@Injectable({
  providedIn: 'root'
})
export class UtenteService {
  private apiUrl = `${environment.apiUrl}/api/utenti`;

  constructor(private http: HttpClient) {}

  getAll(): Observable<Utente[]> {
    return this.http.get<Utente[]>(this.apiUrl);
  }

  getById(id: number): Observable<Utente> {
    return this.http.get<Utente>(`${this.apiUrl}/${id}`);
  }

  getByCodiceFiscale(cf: string): Observable<Utente> {
    return this.http.get<Utente>(`${this.apiUrl}/cf/${cf}`);
  }

  create(utente: Utente): Observable<Utente> {
    return this.http.post<Utente>(this.apiUrl, utente);
  }

  update(id: number, utente: Utente): Observable<Utente> {
    return this.http.put<Utente>(`${this.apiUrl}/${id}`, utente);
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.apiUrl}/${id}`);
  }

  searchByEnte(ente: string): Observable<Utente[]> {
    return this.http.get<Utente[]>(`${this.apiUrl}/ente/${ente}`);
  }
}
