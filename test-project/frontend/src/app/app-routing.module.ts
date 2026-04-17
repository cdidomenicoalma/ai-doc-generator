import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { UtentiListComponent } from './components/utenti-list/utenti-list.component';

const routes: Routes = [
  { path: '', redirectTo: '/utenti', pathMatch: 'full' },
  { path: 'utenti', component: UtentiListComponent },
  { path: 'utenti/:id', component: UtentiListComponent },
  {
    path: 'admin',
    loadChildren: () => import('./modules/admin/admin.module').then(m => m.AdminModule)
  },
  { path: '**', redirectTo: '/utenti' }
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
