import React from 'react';
import { createRoot } from 'react-dom/client';   
import {
  BrowserRouter as Router,
  Route,
  Switch,
  Redirect,
} from 'react-router-dom';

import './index.css';

import Upload from './views/Upload';
import MapAnalysis from './views/MapAnalysis';
import ErrorModal from './views/ErrorModal';
import NotFound from './views/Error';
import AppHeader from './views/AppHeader';
import ProtectedRoute from './views/ProtectedRoute';

const App = () => {
  return (
    <Router>
      <AppHeader />
      <Switch>
        <Route component={Upload} exact path="/" />
        <ProtectedRoute component={ErrorModal} exact path="/errormsg" />
        <ProtectedRoute component={MapAnalysis} exact path="/landing" />
        <Route component={NotFound} path="**" />
        <Redirect to="**" />
      </Switch>
    </Router>
  );
};


const container = document.getElementById('app');
const root = createRoot(container);
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
