
const AppHeader=()=>{
return<>
<header className="openearth-header">
        <div className="openearth-logo-container">
          <img src="/external/vector1503-3faq.svg" alt="OpenEarth Logo" className="openearth-logo" />
          <h1 className="openearth-title">OpenEarth</h1>
        </div>
        <nav className="openearth-nav">
          <ul>
            <li><a href="/">Dashboard</a></li>
            <li><a href="/">Learning</a></li>
            <li><a href="/">Help</a></li>
          </ul>
          <div className="language-selector">
            <div className="flag-icon">🇺🇸</div>
            <span>EN</span>
            <span className="dropdown-arrow">▼</span>
          </div>
        </nav>
      </header>
</>
}
export default AppHeader;