import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
// import AppDebug from './AppDebug.jsx' // Descomente para modo debug
import './index.css'

// StrictMode pode causar double-render em dev, mas não afeta produção
ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
        <App />
        {/* <AppDebug /> */} {/* Descomente para modo debug */}
    </React.StrictMode>,
)
