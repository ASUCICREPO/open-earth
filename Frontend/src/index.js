import React from 'react'
import ReactDOM from 'react-dom'
import {
  BrowserRouter as Router,
  Route,
  Switch,
  Redirect,
} from 'react-router-dom'

import './index.css'

import Upload from './views/Upload'
import DatePicker from './views/DatePicker'
import LandingPage1 from './views/MapAnalysis'
import NotFound from './views/Error'
import AppHeader from './views/AppHeader'

const App = () => {
  return (
    <Router>
     <AppHeader/>
      <Switch>
        <Route component={Upload} exact path="/" />
        <Route component={DatePicker} exact path="/date" />
        <Route component={LandingPage1} exact path="/landing" />
        {/*
        <Route component={OpenEarthDatePicker} exact path="/" />
        <Route component={LandingPage1} exact path="/" />*/}
        
        <Route component={NotFound} path="**" />
        <Redirect to="**" />
      </Switch>
    </Router>
  )
}

ReactDOM.render(<App />, document.getElementById('app'))
