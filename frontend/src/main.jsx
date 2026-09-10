import { render } from "preact";
import "leaflet/dist/leaflet.css";
import "./style.css";
import { App } from "./app.jsx";

render(<App />, document.getElementById("app"));
