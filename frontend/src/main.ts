import './styles.css';
import App from './App.svelte';
import { mount } from 'svelte';

const target = document.getElementById('app');

if (!target) {
  throw new Error('NARATrace konnte den App-Container nicht finden.');
}

const app = mount(App, { target });

export default app;
