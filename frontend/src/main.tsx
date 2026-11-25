import {createRoot} from 'react-dom/client';
import App from './App';
import AuthGate from './components/AuthGate';
import './monitor.css';
import './learning.css';
createRoot(document.getElementById('root')!).render(<AuthGate>{(user,onLogout)=><App key={user.id} user={user} onLogout={onLogout}/>}</AuthGate>);
