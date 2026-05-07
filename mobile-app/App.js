import React, { useEffect, useMemo, useState } from "react";
import { SafeAreaView, ScrollView, StatusBar, StyleSheet, Text, View, Pressable, TextInput } from "react-native";

const diseases = ["Cholera", "Malaria", "Typhoid", "Marburg"];

const plans = {
  Cholera: {
    buy: "ORS, IV fluids, chlorine tabs",
    prevent: "WASH + water safety campaigns",
    invest: "District water labs + UVRI sequencing",
  },
  Malaria: {
    buy: "ACTs, RDT kits, LLINs",
    prevent: "Vector control + CHW surveillance",
    invest: "Entomology labs + rapid diagnostics",
  },
  Typhoid: {
    buy: "Typhoid vaccines + lab reagents",
    prevent: "Food and water hygiene enforcement",
    invest: "Microbiology testing capacity",
  },
  Marburg: {
    buy: "PPE, PCR kits, isolation stocks",
    prevent: "IPC drills + contact tracing",
    invest: "Biosafety and emergency diagnostics",
  },
};

const borderRisk = [
  { name: "Entebbe", score: 72 },
  { name: "Malaba", score: 81 },
  { name: "Mpondwe", score: 76 },
  { name: "Elegu", score: 63 },
];

const API_BASE_URL = "http://127.0.0.1:8000";

const fallbackAlerts = (disease) => [
  `NLP Alert • ${disease} mention velocity is increasing in regional media clusters.`,
  "NLP Alert • Public sentiment indicates concern around diagnostics and treatment access.",
  "NLP Alert • Border-adjacent districts dominate high-risk discussion channels.",
  "NLP Alert • Recommendation: activate daily surveillance briefs and rapid response reviews.",
];

export default function App() {
  const [disease, setDisease] = useState("Cholera");
  const [alerts, setAlerts] = useState(fallbackAlerts("Cholera"));
  const [alertSource, setAlertSource] = useState("fallback");
  const [loadingAlerts, setLoadingAlerts] = useState(false);
  const [apiBaseUrl, setApiBaseUrl] = useState(API_BASE_URL);
  const [apiInput, setApiInput] = useState(API_BASE_URL);
  const [refreshTick, setRefreshTick] = useState(0);

  const projection = useMemo(() => {
    const points = [];
    let infected = 12000;
    const growth = disease === "Marburg" ? 1.04 : disease === "Cholera" ? 1.03 : 1.02;
    for (let day = 0; day <= 10; day += 1) {
      infected = Math.floor(infected * growth);
      points.push({ day: day * 10, infected });
    }
    return points;
  }, [disease]);

  useEffect(() => {
    let mounted = true;
    const run = async () => {
      setLoadingAlerts(true);
      try {
        const response = await fetch(`${apiBaseUrl}/v1/nlp-alerts`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            disease,
            news_mentions: 1200,
            cholera_cases: 38000,
            affected_countries: 22,
          }),
        });
        const payload = await response.json();
        if (!mounted) return;
        if (response.ok && Array.isArray(payload.alerts) && payload.alerts.length > 0) {
          setAlerts(payload.alerts.slice(0, 4));
          setAlertSource(payload.source || "ai");
        } else {
          setAlerts(fallbackAlerts(disease));
          setAlertSource("fallback");
        }
      } catch (error) {
        if (!mounted) return;
        setAlerts(fallbackAlerts(disease));
        setAlertSource("fallback");
      } finally {
        if (mounted) setLoadingAlerts(false);
      }
    };
    run();
    return () => {
      mounted = false;
    };
  }, [disease, apiBaseUrl, refreshTick]);

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="light-content" />
      <ScrollView style={styles.root} contentContainerStyle={styles.container}>
        <Text style={styles.title}>Pathogen Economy Epiforecast</Text>
        <Text style={styles.subtitle}>Uganda epidemic early warning dashboard (mobile prototype)</Text>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>API Settings</Text>
          <TextInput
            style={styles.input}
            value={apiInput}
            onChangeText={setApiInput}
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="http://192.168.1.10:8000"
            placeholderTextColor="#64748b"
          />
          <View style={styles.rowWrap}>
            <Pressable
              style={styles.actionButton}
              onPress={() => {
                const trimmed = apiInput.trim().replace(/\/+$/, "");
                setApiBaseUrl(trimmed || API_BASE_URL);
                setRefreshTick((n) => n + 1);
              }}
            >
              <Text style={styles.actionButtonText}>Apply API URL</Text>
            </Pressable>
          </View>
          <Text style={styles.sourceText}>Current API: {apiBaseUrl}</Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Disease Focus</Text>
          <View style={styles.rowWrap}>
            {diseases.map((d) => (
              <Pressable
                key={d}
                onPress={() => setDisease(d)}
                style={[styles.pill, disease === d ? styles.pillActive : null]}
              >
                <Text style={styles.pillText}>{d}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Global Surveillance Alerts</Text>
          <Text style={styles.sourceText}>Source: {loadingAlerts ? "loading..." : alertSource}</Text>
          {alerts.map((line) => (
            <Text style={styles.alert} key={line}>
              - {line}
            </Text>
          ))}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Travel Risk</Text>
          {borderRisk.map((item) => (
            <View key={item.name} style={styles.riskRow}>
              <Text style={styles.riskName}>{item.name}</Text>
              <View style={styles.barTrack}>
                <View style={[styles.barFill, { width: `${item.score}%` }]} />
              </View>
              <Text style={styles.riskScore}>{item.score}%</Text>
            </View>
          ))}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>SEIR Projection Snapshot (100 days)</Text>
          {projection.map((p) => (
            <Text style={styles.point} key={`${p.day}-${p.infected}`}>
              Day {p.day}: {p.infected.toLocaleString()} infected (simulated)
            </Text>
          ))}
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Uganda Action Plan</Text>
          <Text style={styles.planLine}>Buy: {plans[disease].buy}</Text>
          <Text style={styles.planLine}>Prevent: {plans[disease].prevent}</Text>
          <Text style={styles.planLine}>Invest: {plans[disease].invest}</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0b1220" },
  root: { flex: 1, backgroundColor: "#0b1220" },
  container: { padding: 16, gap: 14, paddingBottom: 42 },
  title: { color: "#f8fafc", fontSize: 24, fontWeight: "700" },
  subtitle: { color: "#cbd5e1", fontSize: 13, marginTop: 4 },
  card: {
    backgroundColor: "#111827",
    borderColor: "#1f2937",
    borderWidth: 1,
    borderRadius: 12,
    padding: 12,
  },
  cardTitle: { color: "#e2e8f0", fontWeight: "700", marginBottom: 8 },
  rowWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  pill: { borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, backgroundColor: "#1f2937" },
  pillActive: { backgroundColor: "#22c55e" },
  pillText: { color: "#f8fafc", fontSize: 12, fontWeight: "600" },
  alert: { color: "#fcd34d", marginBottom: 4, fontSize: 12 },
  sourceText: { color: "#93c5fd", marginBottom: 8, fontSize: 11 },
  input: {
    backgroundColor: "#0f172a",
    borderColor: "#334155",
    borderWidth: 1,
    borderRadius: 8,
    color: "#e2e8f0",
    paddingHorizontal: 10,
    paddingVertical: 8,
    marginBottom: 10,
    fontSize: 12,
  },
  actionButton: {
    backgroundColor: "#22c55e",
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  actionButtonText: { color: "#022c22", fontWeight: "700", fontSize: 12 },
  riskRow: { flexDirection: "row", alignItems: "center", marginBottom: 8, gap: 8 },
  riskName: { color: "#e2e8f0", width: 70, fontSize: 12 },
  barTrack: { flex: 1, height: 8, backgroundColor: "#1f2937", borderRadius: 999, overflow: "hidden" },
  barFill: { height: "100%", backgroundColor: "#ef4444" },
  riskScore: { color: "#e2e8f0", width: 38, fontSize: 12, textAlign: "right" },
  point: { color: "#93c5fd", fontSize: 12, marginBottom: 3 },
  planLine: { color: "#bbf7d0", marginBottom: 4, fontSize: 12 },
});
