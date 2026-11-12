/*
===================================================================
Demand Prediction and Resource Optimization - browser logic
Every function here talks to a Flask route in app.py using fetch().
===================================================================
*/

/* ---------- Flask backend connection ---------- */

const API_BASE = location.port === "5000"
    ? ""
    : "http://127.0.0.1:5000";


/* ---------- Small helpers ---------- */

let foodItems = [];
let records = [];
let facilities = [];
let trendChart = null;
let wasteChart = null;

const money = (n) => "₹" + Number(n || 0).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
});

const qty = (n) => Number(n || 0).toLocaleString("en-IN", {
    maximumFractionDigits: 0
});

const byId = (id) => document.getElementById(id);


function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[c]);
}


function todayStr() {
    const d = new Date();
    const offset = d.getTimezoneOffset();
    d.setMinutes(d.getMinutes() - offset);
    return d.toISOString().slice(0, 10);
}


function nowLocalStr() {
    const d = new Date();
    const offset = d.getTimezoneOffset();
    d.setMinutes(d.getMinutes() - offset);
    return d.toISOString().slice(0, 16);
}


function showToast(message, type = "success") {
    const container = byId("toast-container");

    if (!container) {
        alert(message);
        return;
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => toast.remove(), 4000);
}


/* ---------- API helper ---------- */

async function api(url, method = "GET", body = null) {

    const options = {
        method,
        headers: {}
    };

    if (body !== null) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(body);
    }

    let response;

    try {

        response = await fetch(API_BASE + url, options);

    } catch (error) {

        throw new Error(
            "Cannot connect to Flask. Start the backend using python app.py."
        );

    }

    const text = await response.text();

    let data = {};

    try {
        data = text ? JSON.parse(text) : {};
    } catch {
        data = { error: text || "Invalid server response." };
    }

    if (!response.ok) {
        throw new Error(
            data.error || data.message || `Server error (${response.status})`
        );
    }

    return data;
}


async function runWithButton(buttonId, action) {

    const button = byId(buttonId);

    if (button) {
        button.disabled = true;
    }

    try {

        await action();

    } catch (error) {

        showToast(error.message || "Something went wrong.", "error");

    } finally {

        if (button) {
            button.disabled = false;
        }

    }
}


function badgeForStatus(status) {

    const safe = esc(status || "Unknown");

    const normalized = String(status || "").toLowerCase();

    let cls = "badge-neutral";

    if (
        ["available", "donated", "completed", "accepted", "collected"].includes(normalized)
    ) {
        cls = "badge-success";
    } else if (
        ["pending", "requested", "pickup scheduled", "reserved"].includes(normalized)
    ) {
        cls = "badge-warning";
    } else if (
        ["discarded", "rejected", "cancelled"].includes(normalized)
    ) {
        cls = "badge-danger";
    }

    return `<span class="badge ${cls}">${safe}</span>`;
}


/* ===================================================================
   NAVIGATION
   =================================================================== */

function showTab(name) {

    document.querySelectorAll(".tab").forEach((tab) => {
        tab.classList.toggle("active", tab.id === name);
    });

    document.querySelectorAll(".nav-btn").forEach((button) => {
        button.classList.toggle(
            "active",
            button.dataset.tab === name
        );
    });

    if (name === "dashboard") loadDashboard();
    if (name === "food-items") loadFoodItems();
    if (name === "daily-records") loadRecords();
    if (name === "predictions") loadPredictions();
    if (name === "surplus") loadSurplus();
    if (name === "facilities") loadFacilities(currentFacilityType || "");
    if (name === "storage") loadStorage();
    if (name === "inventory") loadPhase3Inventory();
    if (name === "donations-v3") loadPhase3Donations();
    if (name === "simulation") {
        loadPhase3Forecast();
        ensureFoodItems();
    }
    if (name === "audit") loadPhase3Audit();

    if (name === "facilities" && mapInstance) {
        setTimeout(() => mapInstance.invalidateSize(), 100);
    }
}


/* ---------- Food item dropdowns ---------- */

async function ensureFoodItems() {

    if (!foodItems.length) {
        foodItems = await api("/api/food-items");
    }

    fillItemSelects();
}


function fillItemSelects() {

    const selects = [
        "record-item",
        "pred-item",
        "surplus-item",
        "storage-item",
        "sim-item"
    ];

    selects.forEach((id) => {

        const select = byId(id);

        if (!select) return;

        const previous = select.value;

        select.innerHTML = foodItems.map((item) => `
            <option value="${item.item_id}">
                ${esc(item.item_name)}
            </option>
        `).join("");

        if (previous) {
            select.value = previous;
        }

    });
}


/* ===================================================================
   DASHBOARD
   =================================================================== */

async function loadDashboard() {

    const d = await api("/api/dashboard");

    byId("stat-prepared").textContent = qty(d.total_prepared);
    byId("stat-sold").textContent = qty(d.total_sold);
    byId("stat-leftover").textContent = qty(d.total_leftover);

    byId("stat-waste").textContent = money(d.total_waste_cost);

    const percent = d.total_prepared
        ? (d.total_leftover / d.total_prepared) * 100
        : 0;

    byId("stat-waste-pct").textContent =
        `${percent.toFixed(1)}% of prepared`;

    byId("stat-items").textContent = qty(d.total_items);
    byId("stat-records").textContent = qty(d.total_records);
    byId("stat-surplus").textContent = qty(d.available_surplus);

    const body = byId("dash-table-body");

    body.innerHTML = (d.by_item || []).map((row) => `
        <tr>
            <td>${esc(row.item_name)}</td>
            <td class="num">${qty(row.prepared)}</td>
            <td class="num">${qty(row.sold)}</td>
            <td class="num">${qty(row.leftover)}</td>
            <td class="num">${money(row.waste_cost)}</td>
        </tr>
    `).join("") || `
        <tr><td colspan="5" class="empty">No records yet.</td></tr>
    `;

    renderCharts(d);
}


/* ---------- Dashboard charts ---------- */

function renderCharts(d) {

    if (typeof Chart === "undefined") {
        const note = byId("chart-note");
        if (note) {
            note.hidden = false;
            note.textContent = "Charts could not load. Check your internet connection.";
        }
        return;
    }

    const trendCanvas = byId("chart-trend");
    const wasteCanvas = byId("chart-waste");

    if (trendChart) trendChart.destroy();
    if (wasteChart) wasteChart.destroy();

    const trend = d.trend || [];

    trendChart = new Chart(trendCanvas, {
        type: "line",
        data: {
            labels: trend.map((r) => r.record_date),
            datasets: [
                {
                    label: "Prepared",
                    data: trend.map((r) => r.prepared),
                    tension: 0.3
                },
                {
                    label: "Sold",
                    data: trend.map((r) => r.sold),
                    tension: 0.3
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false
        }
    });

    const items = d.by_item || [];

    wasteChart = new Chart(wasteCanvas, {
        type: "bar",
        data: {
            labels: items.map((r) => r.item_name),
            datasets: [
                {
                    label: "Waste cost",
                    data: items.map((r) => r.waste_cost)
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
}
/* ===================================================================
   FOOD ITEMS
   =================================================================== */

async function loadFoodItems() {

    foodItems = await api("/api/food-items");

    fillItemSelects();

    const body = byId("food-table-body");

    body.innerHTML = foodItems.map((item) => `
        <tr>
            <td>${esc(item.item_name)}</td>
            <td>${esc(item.category)}</td>
            <td class="num">${money(item.selling_price)}</td>
            <td class="num">${money(item.production_cost)}</td>
            <td class="num">${qty(item.record_count)}</td>
            <td class="num">${qty(item.total_sold)}</td>
            <td>
                <button class="btn btn-small"
                    onclick="editFoodItem(${item.item_id})">Edit</button>
                <button class="btn btn-small btn-danger"
                    onclick="deleteFoodItem(${item.item_id})">Delete</button>
            </td>
        </tr>
    `).join("") || `
        <tr><td colspan="7" class="empty">No food items added yet.</td></tr>
    `;
}


function submitFoodItem(event) {

    event.preventDefault();

    runWithButton("food-submit", async () => {

        const id = byId("item-id").value;

        const data = {
            item_name: byId("item-name").value.trim(),
            category: byId("item-category").value.trim(),
            selling_price: byId("item-price").value,
            production_cost: byId("item-cost").value
        };

        await api(
            id ? `/api/food-items/${id}` : "/api/food-items",
            id ? "PUT" : "POST",
            data
        );

        cancelFoodEdit();

        await loadFoodItems();

        showToast(
            id ? "Food item updated." : "Food item added."
        );

    });
}


function editFoodItem(id) {

    const item = foodItems.find(
        (row) => Number(row.item_id) === Number(id)
    );

    if (!item) return;

    byId("item-id").value = item.item_id;
    byId("item-name").value = item.item_name;
    byId("item-category").value = item.category;
    byId("item-price").value = item.selling_price;
    byId("item-cost").value = item.production_cost;

    byId("food-form-title").textContent = "Edit Food Item";
    byId("food-submit").textContent = "Save Changes";
    byId("food-cancel").hidden = false;

    byId("food-form").scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}


function cancelFoodEdit() {

    byId("food-form").reset();

    byId("item-id").value = "";

    byId("food-form-title").textContent = "Add a Food Item";
    byId("food-submit").textContent = "Add Item";
    byId("food-cancel").hidden = true;
}


async function deleteFoodItem(id) {

    if (!confirm("Delete this food item?")) return;

    try {

        await api(`/api/food-items/${id}`, "DELETE");

        await loadFoodItems();

        showToast("Food item deleted.");

    } catch (error) {

        showToast(error.message, "error");

    }
}


/* ===================================================================
   DAILY RECORDS
   =================================================================== */

async function loadRecords() {

    await ensureFoodItems();

    records = await api("/api/daily-records");

    const body = byId("record-table-body");

    body.innerHTML = records.map((row) => `
        <tr>
            <td>${esc(row.record_date)}</td>
            <td>${esc(row.item_name)}</td>
            <td class="num">${qty(row.prepared_qty)}</td>
            <td class="num">${qty(row.sold_qty)}</td>
            <td class="num">${qty(row.leftover_qty)}</td>
            <td class="num">${money(row.waste_cost)}</td>
            <td>
                <button class="btn btn-small"
                    onclick="editRecord(${row.record_id})">Edit</button>
                <button class="btn btn-small btn-danger"
                    onclick="deleteRecord(${row.record_id})">Delete</button>
            </td>
        </tr>
    `).join("") || `
        <tr><td colspan="7" class="empty">No daily records yet.</td></tr>
    `;

    updateRecordPreview();
}


function updateRecordPreview() {

    const prepared = Number(
        byId("record-prepared").value || 0
    );

    const sold = Number(
        byId("record-sold").value || 0
    );

    const preview = byId("record-preview");

    if (sold > prepared) {

        preview.textContent =
            "Sold quantity cannot exceed prepared quantity.";

        preview.classList.add("text-danger");

        return;
    }

    preview.classList.remove("text-danger");

    preview.textContent =
        `Leftover: ${qty(Math.max(0, prepared - sold))}`;
}


function submitRecord(event) {

    event.preventDefault();

    runWithButton("record-submit", async () => {

        const id = byId("record-id").value;

        const data = {
            record_date: byId("record-date").value,
            item_id: byId("record-item").value,
            prepared_qty: byId("record-prepared").value,
            sold_qty: byId("record-sold").value
        };

        if (Number(data.sold_qty) > Number(data.prepared_qty)) {
            throw new Error(
                "Sold quantity cannot be more than prepared quantity."
            );
        }

        await api(
            id ? `/api/daily-records/${id}` : "/api/daily-records",
            id ? "PUT" : "POST",
            data
        );

        cancelRecordEdit();

        await loadRecords();

        showToast(
            id ? "Daily record updated." : "Daily record saved."
        );

    });
}


function editRecord(id) {

    const row = records.find(
        (r) => Number(r.record_id) === Number(id)
    );

    if (!row) return;

    byId("record-id").value = row.record_id;
    byId("record-date").value = row.record_date;
    byId("record-item").value = row.item_id;
    byId("record-prepared").value = row.prepared_qty;
    byId("record-sold").value = row.sold_qty;

    byId("record-form-title").textContent = "Edit Daily Record";
    byId("record-submit").textContent = "Save Changes";
    byId("record-cancel").hidden = false;

    updateRecordPreview();

    byId("record-form").scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}


function cancelRecordEdit() {

    byId("record-form").reset();

    byId("record-id").value = "";

    byId("record-date").value = todayStr();

    byId("record-form-title").textContent = "Add a Daily Record";
    byId("record-submit").textContent = "Save Record";
    byId("record-cancel").hidden = true;

    updateRecordPreview();
}


async function deleteRecord(id) {

    if (!confirm("Delete this daily record?")) return;

    try {

        await api(`/api/daily-records/${id}`, "DELETE");

        await loadRecords();

        showToast("Daily record deleted.");

    } catch (error) {

        showToast(error.message, "error");

    }
}


/* ===================================================================
   DEMAND PREDICTION
   =================================================================== */

async function loadPredictions() {

    await ensureFoodItems();

    const rows = await api("/api/predictions");

    const body = byId("pred-table-body");

    body.innerHTML = rows.map((row) => `
        <tr>
            <td>${esc(row.item_name)}</td>
            <td>${esc(row.prediction_date)}</td>
            <td class="num">${qty(row.records_used)}</td>
            <td class="num">${qty(row.avg_sales)}</td>
            <td class="num">${qty(row.buffer_percent)}%</td>
            <td class="num"><strong>${qty(row.recommended_qty)}</strong></td>
            <td>
                <button class="btn btn-small btn-danger"
                    onclick="deletePrediction(${row.prediction_id})">
                    Delete
                </button>
            </td>
        </tr>
    `).join("") || `
        <tr><td colspan="7" class="empty">No predictions saved yet.</td></tr>
    `;

    byId("pred-result").innerHTML = "";
}


function runPrediction(event) {

    event.preventDefault();

    runWithButton("pred-submit", async () => {

        const result = await api("/api/predictions", "POST", {
            item_id: byId("pred-item").value
        });

        const output = result.results || [];

        byId("pred-result").innerHTML = output.map((row) => `
            <div class="prediction-result">
                <h3>${esc(row.item_name)}</h3>
                <p>Prediction date: <strong>${esc(row.prediction_date)}</strong></p>
                <p>Average sales: <strong>${qty(row.avg_sales)}</strong></p>
                <p>Records used: <strong>${qty(row.records_used)}</strong></p>
                <p>Recommended preparation: <strong>${qty(row.recommended_qty)}</strong></p>
            </div>
        `).join("");

        await loadPredictions();

        showToast(result.message || "Prediction saved.");

    });
}


async function deletePrediction(id) {

    if (!confirm("Delete this prediction?")) return;

    try {

        await api(`/api/predictions/${id}`, "DELETE");

        await loadPredictions();

        showToast("Prediction deleted.");

    } catch (error) {

        showToast(error.message, "error");

    }
}
/* ===================================================================
   SURPLUS FOOD
   =================================================================== */

let surplusRows = [];
let surplusOptions = [];


async function loadSurplus() {

    const [result, options] = await Promise.all([
        api("/api/surplus"),
        api("/api/surplus/options")
    ]);

    surplusRows = result.rows || [];
    surplusOptions = options || [];

    const recordSelect = byId("surplus-record");

    recordSelect.innerHTML = surplusOptions.map((row) => `
        <option value="${row.record_id}">
            ${esc(row.record_date)} - ${esc(row.item_name)}
            (leftover: ${qty(row.remaining)})
        </option>
    `).join("");

    byId("surplus-facility").innerHTML = facilityOptions();

    renderSurplusTable(result);
}


function facilityOptions(selectedId = "") {

    return `
        <option value="">Select facility</option>
        ${facilities.map((facility) => `
            <option value="${facility.facility_id}"
                ${String(facility.facility_id) === String(selectedId) ? "selected" : ""}>
                ${esc(facility.facility_name)}
            </option>
        `).join("")}
    `;
}


function onSurplusRecordChange() {

    const selected = surplusOptions.find(
        (row) => String(row.record_id) === String(byId("surplus-record").value)
    );

    if (selected) {
        byId("surplus-qty").max = selected.remaining;
        byId("surplus-qty").value = selected.remaining;
    }
}


function renderSurplusTable(result) {

    const summary = result.summary || [];

    byId("surplus-summary").innerHTML = summary.map((row) => `
        <span class="chip">
            ${esc(row.status)}:
            <strong>${qty(row.total_qty)}</strong>
            &nbsp;(${money(row.cost_value)})
        </span>
    `).join("");

    byId("surplus-table-body").innerHTML =
        surplusRows.map((row) => `
            <tr>
                <td>${esc(row.record_date)}</td>
                <td>${esc(row.item_name)}</td>
                <td class="num">${qty(row.quantity)}</td>
                <td class="num">${money(row.cost_value)}</td>
                <td>${badgeForStatus(row.status)}</td>
                <td>${esc(row.facility_name || "—")}</td>
                <td>${esc(row.notes || "")}</td>
                <td>
                    <button class="btn btn-small"
                        onclick="changeSurplusStatus(${row.surplus_id})">
                        Status
                    </button>
                    <button class="btn btn-small btn-danger"
                        onclick="deleteSurplus(${row.surplus_id})">
                        Delete
                    </button>
                </td>
            </tr>
        `).join("") || `
            <tr><td colspan="8" class="empty">No surplus entries yet.</td></tr>
        `;
}


function submitSurplus(event) {

    event.preventDefault();

    runWithButton("surplus-submit", async () => {

        const data = {
            record_id: byId("surplus-record").value,
            quantity: byId("surplus-qty").value,
            status: byId("surplus-status").value,
            facility_id: byId("surplus-facility").value || null,
            notes: byId("surplus-notes").value.trim()
        };

        await api("/api/surplus", "POST", data);

        byId("surplus-form").reset();

        await loadSurplus();

        showToast("Surplus entry saved.");

    });
}


async function changeSurplusStatus(id) {

    const row = surplusRows.find(
        (r) => Number(r.surplus_id) === Number(id)
    );

    if (!row) return;

    const status = prompt(
        "Enter status: Available, Donated, Composted, Discarded",
        row.status
    );

    if (!status) return;

    const allowed = [
        "Available",
        "Donated",
        "Composted",
        "Discarded"
    ];

    const matched = allowed.find(
        (s) => s.toLowerCase() === status.trim().toLowerCase()
    );

    if (!matched) {
        showToast("Invalid status.", "error");
        return;
    }

    try {

        await api(`/api/surplus/${id}`, "PUT", {
            status: matched,
            facility_id: row.facility_id || null
        });

        await loadSurplus();

        showToast("Surplus status updated.");

    } catch (error) {

        showToast(error.message, "error");

    }
}


async function deleteSurplus(id) {

    if (!confirm("Delete this surplus entry?")) return;

    try {

        await api(`/api/surplus/${id}`, "DELETE");

        await loadSurplus();

        showToast("Surplus entry deleted.");

    } catch (error) {

        showToast(error.message, "error");

    }
}


/* ===================================================================
   BHIMTAL OPENSTREETMAP
   =================================================================== */

let mapInstance = null;
let mapMarkers = [];
let mapCircle = null;
let nearbyPlaces = [];
let currentFacilityType = "";


function facilityIcon(category) {

    const icons = {
        "Food bank": "🍲",
        "Social facility": "🤝",
        "NGO": "❤️",
        "Recycling point": "♻️",
        "Waste site": "🗑️",
        "Civic office": "🏛️"
    };

    return icons[category] || "📍";
}


function initBhimtalMap() {

    if (mapInstance) return;

    const mapElement = byId("bhimtal-map");

    if (!mapElement || typeof L === "undefined") {
        return;
    }

    const center = [29.3500, 79.5667];

    mapInstance = L.map("bhimtal-map").setView(center, 12);

    L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        }
    ).addTo(mapInstance);

    mapCircle = L.circle(center, {
        radius: 20000,
        color: "#2563eb",
        weight: 2,
        fillOpacity: 0.04
    }).addTo(mapInstance);

    mapCircle.bindPopup("20 km search radius from Bhimtal centre");

    setTimeout(() => mapInstance.invalidateSize(), 200);
}


function distanceKm(lat1, lon1, lat2, lon2) {

    const toRad = (value) => value * Math.PI / 180;

    const R = 6371;

    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);

    const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos(toRad(lat1)) *
        Math.cos(toRad(lat2)) *
        Math.sin(dLon / 2) ** 2;

    return 2 * R * Math.atan2(
        Math.sqrt(a),
        Math.sqrt(1 - a)
    );
}


function renderNearbyPlaces() {

    if (!mapInstance) initBhimtalMap();

    if (!mapInstance) return;

    mapMarkers.forEach((marker) => {
        mapInstance.removeLayer(marker);
    });

    mapMarkers = [];

    const filtered = nearbyPlaces.filter((place) => {
        return !currentFacilityType ||
            place.category === currentFacilityType;
    });

    filtered.forEach((place) => {

        const marker = L.marker([
            place.lat,
            place.lon
        ]).addTo(mapInstance);

        const distance = distanceKm(
            29.3500,
            79.5667,
            place.lat,
            place.lon
        );

        const popup = `
            <strong>${esc(place.name)}</strong><br>
            ${facilityIcon(place.category)}
            ${esc(place.category)}<br>
            ${distance.toFixed(1)} km from Bhimtal<br>
            ${esc(place.address || "Address not listed")}<br>
            <a href="${esc(place.osm_url)}"
               target="_blank" rel="noopener">
               View on OpenStreetMap
            </a>
        `;

        marker.bindPopup(popup);

        mapMarkers.push(marker);

    });

    const list = byId("facility-list");

    list.innerHTML = filtered.map((place) => {

        const distance = distanceKm(
            29.3500,
            79.5667,
            place.lat,
            place.lon
        );

        return `
            <article class="facility-card">
                <div class="facility-icon">
                    ${facilityIcon(place.category)}
                </div>
                <div>
                    <h3>${esc(place.name)}</h3>
                    <span class="facility-type">${esc(place.category)}</span>
                    <p>${esc(place.address || "Address not listed")}</p>
                    <p>${distance.toFixed(1)} km from Bhimtal</p>
                    ${place.phone
                        ? `<p>Phone: ${esc(place.phone)}</p>`
                        : ""}
                    <a href="${esc(place.osm_url)}"
                       target="_blank" rel="noopener">
                        View map details
                    </a>
                </div>
            </article>
        `;
    }).join("") || `
        <p class="empty">
            No mapped places found for this category.
        </p>
    `;

    byId("map-status").textContent =
        `${filtered.length} mapped place(s) shown within the Bhimtal search area.`;
}


async function loadFacilities(type = "") {

    currentFacilityType = type;

    initBhimtalMap();

    byId("map-status").textContent =
        "Fetching mapped places from OpenStreetMap...";

    try {

        const result = await api("/api/nearby-facilities");

        nearbyPlaces = result.places || [];

        renderNearbyPlaces();

    } catch (error) {

        byId("map-status").textContent =
            "Map data could not be loaded. Check your internet connection and try again.";

        showToast(error.message, "error");

    }
}


function filterFacilities(type) {

    currentFacilityType = type;

    document.querySelectorAll(".filter-btn").forEach((button) => {
        button.classList.toggle(
            "active",
            button.dataset.type === type
        );
    });

    renderNearbyPlaces();
}
/* ===================================================================
   FOOD STORAGE
   =================================================================== */

let storageRows = [];


async function loadStorage() {

    await ensureFoodItems();

    storageRows = await api("/api/storage");

    const body = byId("storage-table-body");

    body.innerHTML = storageRows.map((row) => {

        const alerts = row.alerts || [];

        const alertHtml = alerts.length
            ? alerts.map((alert) => `
                <div class="storage-alert ${esc(alert.level)}">
                    ${esc(alert.text)}
                </div>
            `).join("")
            : `<span class="badge badge-success">No alert</span>`;

        return `
            <tr>
                <td>${esc(row.item_name)}</td>
                <td>${esc(row.prep_time)}</td>
                <td class="num">${qty(row.hours_since_prep)}</td>
                <td>${esc(row.storage_method)}</td>
                <td class="num">
                    ${row.temperature_c === null
                        ? "—"
                        : `${esc(row.temperature_c)} °C`}
                </td>
                <td>${esc(row.notes || "")}</td>
                <td>${alertHtml}</td>
                <td>
                    <button class="btn btn-small btn-danger"
                        onclick="deleteStorage(${row.storage_id})">
                        Delete
                    </button>
                </td>
            </tr>
        `;

    }).join("") || `
        <tr><td colspan="8" class="empty">No storage records yet.</td></tr>
    `;
}


function submitStorage(event) {

    event.preventDefault();

    runWithButton("storage-submit", async () => {

        const data = {
            item_id: byId("storage-item").value,
            prep_time: byId("storage-time").value,
            storage_method: byId("storage-method").value,
            temperature_c: byId("storage-temp").value || null,
            notes: byId("storage-notes").value.trim()
        };

        await api("/api/storage", "POST", data);

        byId("storage-form").reset();

        byId("storage-time").value = nowLocalStr();

        await loadStorage();

        showToast("Storage record saved.");

    });
}


async function deleteStorage(id) {

    if (!confirm("Delete this storage record?")) return;

    try {

        await api(`/api/storage/${id}`, "DELETE");

        await loadStorage();

        showToast("Storage record deleted.");

    } catch (error) {

        showToast(error.message, "error");

    }
}


/* ===================================================================
   BACKEND CONNECTION
   =================================================================== */

async function connectAndStart() {

    const warning = byId("file-warning");
    const message = byId("conn-message");
    const flaskHint = byId("conn-hint-flask");
    const dbHint = byId("conn-hint-db");

    if (message) {
        message.textContent = "Connecting to the backend...";
    }

    if (flaskHint) flaskHint.hidden = false;
    if (dbHint) dbHint.hidden = true;

    try {

        await api("/api/health");

        if (warning) warning.hidden = true;

        await ensureFoodItems();

        if (byId("record-date")) {
            byId("record-date").value = todayStr();
        }

        if (byId("storage-time")) {
            byId("storage-time").value = nowLocalStr();
        }

        await loadDashboard();

        showToast("Connected to the database.");

    } catch (error) {

        if (warning) warning.hidden = false;

        if (message) {
            message.textContent = error.message;
        }

        if (String(error.message).toLowerCase().includes("database")) {
            if (flaskHint) flaskHint.hidden = true;
            if (dbHint) dbHint.hidden = false;
        }

    }
}


/* ===================================================================
   PHASE 3: INVENTORY, DONATIONS, FORECAST & AUDIT
   =================================================================== *//* ===================================================================
   PHASE 3: INVENTORY
   =================================================================== */

async function loadPhase3Inventory() {

    const result = await api("/api/phase3/summary");

    const rows = result.inventory || [];

    byId("inventory-body").innerHTML = rows.map((row) => `
        <tr>
            <td>${esc(row.ingredient_name)}</td>
            <td>${esc(row.unit)}</td>
            <td class="num">${qty(row.quantity)}</td>
            <td class="num">${qty(row.reorder_level)}</td>
            <td>
                ${Number(row.low_stock)
                    ? badgeForStatus("Low Stock")
                    : badgeForStatus("Available")}
            </td>
            <td>
                <form onsubmit="adjustInventory(event, ${row.ingredient_id})"
                    class="inline-form">
                    <input type="number" name="quantity"
                        min="0" step="0.01" required
                        placeholder="New stock">
                    <button class="btn btn-small" type="submit">
                        Update
                    </button>
                </form>
            </td>
        </tr>
    `).join("") || `
        <tr><td colspan="6" class="empty">No ingredients added yet.</td></tr>
    `;

    const form = byId("ingredient-form");

    if (form && !form.dataset.bound) {

        form.dataset.bound = "true";

        form.addEventListener("submit", async (event) => {

            event.preventDefault();

            try {

                await api("/api/phase3/ingredients", "POST", {
                    ingredient_name: byId("ingredient-name").value,
                    unit: byId("ingredient-unit").value,
                    reorder_level: byId("ingredient-reorder").value,
                    quantity: byId("ingredient-quantity").value
                });

                form.reset();

                await loadPhase3Inventory();

                showToast("Ingredient added successfully.");

            } catch (error) {

                showToast(error.message, "error");

            }

        });

    }
}


async function adjustInventory(event, id) {

    event.preventDefault();

    const form = event.currentTarget;

    const quantity = form.elements.quantity.value;

    try {

        await api(`/api/phase3/inventory/${id}`, "PUT", {
            quantity
        });

        await loadPhase3Inventory();

        showToast("Inventory updated.");

    } catch (error) {

        showToast(error.message, "error");

    }
}


/* ===================================================================
   PHASE 3: DONATION WORKFLOW
   =================================================================== */

async function loadPhase3Donations() {

    const result = await api("/api/phase3/summary");

    const rows = result.donations || [];

    const surplusOptions = await api("/api/surplus");

    const available = (surplusOptions.rows || []).filter(
        (row) => row.status === "Available"
    );

    byId("donation-surplus").innerHTML = available.map((row) => `
        <option value="${row.surplus_id}">
            ${esc(row.item_name)} — ${qty(row.quantity)} units
        </option>
    `).join("");

    const facilityRows = await api("/api/facilities");

    byId("donation-facility").innerHTML = `
        <option value="">Choose facility</option>
        ${(facilityRows || []).map((facility) => `
            <option value="${facility.facility_id}">
                ${esc(facility.facility_name)}
            </option>
        `).join("")}
    `;

    byId("donation-body").innerHTML = rows.map((row) => `
        <tr>
            <td>${row.donation_id}</td>
            <td>${esc(row.item_name)}</td>
            <td>${qty(row.requested_quantity)}</td>
            <td>${esc(row.facility_name || "—")}</td>
            <td>${badgeForStatus(row.status)}</td>
            <td>
                <select onchange="changeDonationStatus(${row.donation_id}, this.value)">
                    ${[
                        "Requested",
                        "Accepted",
                        "Rejected",
                        "Pickup Scheduled",
                        "Collected",
                        "Cancelled"
                    ].map((status) => `
                        <option value="${status}"
                            ${row.status === status ? "selected" : ""}>
                            ${status}
                        </option>
                    `).join("")}
                </select>
            </td>
        </tr>
    `).join("") || `
        <tr><td colspan="6" class="empty">No donation requests yet.</td></tr>
    `;

    const form = byId("donation-form");

    if (form && !form.dataset.bound) {

        form.dataset.bound = "true";

        form.addEventListener("submit", async (event) => {

            event.preventDefault();

            try {

                await api("/api/phase3/donations", "POST", {
                    surplus_id: byId("donation-surplus").value,
                    requested_quantity: byId("donation-quantity").value,
                    facility_id: byId("donation-facility").value || null,
                    notes: byId("donation-notes").value
                });

                form.reset();

                await loadPhase3Donations();

                showToast("Donation request created.");

            } catch (error) {

                showToast(error.message, "error");

            }

        });

    }
}


async function changeDonationStatus(id, status) {

    try {

        let pickup = null;

        if (status === "Pickup Scheduled") {

            pickup = prompt(
                "Enter pickup time (YYYY-MM-DDTHH:MM):"
            );

            if (!pickup) return;

        }

        await api(`/api/phase3/donations/${id}`, "PUT", {
            status,
            pickup_time: pickup
        });

        await loadPhase3Donations();

        showToast("Donation status updated.");

    } catch (error) {

        showToast(error.message, "error");

    }
}


/* ===================================================================
   PHASE 3: FORECAST
   =================================================================== */

async function loadPhase3Forecast() {

    const rows = await api("/api/phase3/forecast");

    byId("forecast-body").innerHTML = rows.map((row) => `
        <tr>
            <td>${esc(row.item_name)}</td>
            <td>${qty(row.records_used)}</td>
            <td>${qty(row.avg_sales)}</td>
            <td><strong>${qty(row.recommended_qty)}</strong></td>
        </tr>
    `).join("") || `
        <tr><td colspan="4" class="empty">No sales records available.</td></tr>
    `;
}


/* ===================================================================
   PHASE 3: AUDIT LOG
   =================================================================== */

async function loadPhase3Audit() {

    const rows = await api("/api/phase3/audit");

    byId("audit-body").innerHTML = rows.map((row) => `
        <tr>
            <td>${esc(row.created_at)}</td>
            <td>${esc(row.entity_type)}</td>
            <td>${qty(row.entity_id)}</td>
            <td>${esc(row.action_type)}</td>
            <td>${esc(row.details)}</td>
        </tr>
    `).join("") || `
        <tr><td colspan="5" class="empty">No audit logs yet.</td></tr>
    `;
}


/* ===================================================================
   WHAT-IF SIMULATION
   =================================================================== */

async function runSimulation(event) {

    event.preventDefault();

    try {

        const result = await api("/api/phase3/simulation", "POST", {
            item_id: byId("sim-item").value,
            expected_demand: byId("sim-demand").value,
            buffer_percent: byId("sim-buffer").value
        });

        byId("simulation-result").innerHTML = `
            <h3>Simulation Results</h3>
            <div class="result-grid">
                <div>
                    <span>Expected demand</span>
                    <strong>${qty(result.expected_demand)}</strong>
                </div>
                <div>
                    <span>Recommended preparation</span>
                    <strong>${qty(result.recommended_preparation)}</strong>
                </div>
                <div>
                    <span>Estimated leftover</span>
                    <strong>${qty(result.estimated_leftover)}</strong>
                </div>
                <div>
                    <span>Estimated waste cost</span>
                    <strong>${money(result.estimated_waste_cost)}</strong>
                </div>
                <div>
                    <span>Estimated revenue</span>
                    <strong>${money(result.estimated_revenue)}</strong>
                </div>
            </div>
        `;

    } catch (error) {

        showToast(error.message, "error");

    }
}


/* ===================================================================
   INITIALIZATION
   =================================================================== */

document.addEventListener("DOMContentLoaded", () => {

    if (byId("simulation-form")) {
        byId("simulation-form").addEventListener(
            "submit",
            runSimulation
        );
    }

    if (byId("record-date")) {
        byId("record-date").value = todayStr();
    }

    if (byId("storage-time")) {
        byId("storage-time").value = nowLocalStr();
    }

    connectAndStart();

});
