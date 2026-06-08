package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"
)

type PowerMetrics struct {
	AverageConsumedWatts float64 `json:"AverageConsumedWatts"`
	MaxConsumedWatts     float64 `json:"MaxConsumedWatts"`
	MinConsumedWatts     float64 `json:"MinConsumedWatts"`
}

type PowerControl struct {
	PowerConsumedWatts float64      `json:"PowerConsumedWatts"`
	PowerCapacityWatts float64      `json:"PowerCapacityWatts"`
	PowerMetrics       PowerMetrics `json:"PowerMetrics"`
}

type RedfishPowerResponse struct {
	PowerControl []PowerControl `json:"PowerControl"`
}

type Node struct {
	Name string
	URL  string
}

var nodes = []Node{
	{"worker-node-1", "http://localhost:8000/redfish/v1/Chassis/1U/Power"},
	{"worker-node-2", "http://localhost:8001/redfish/v1/Chassis/1U/Power"},
	{"worker-node-3", "http://localhost:8002/redfish/v1/Chassis/1U/Power"},
}

func fetchPower(node Node) (*PowerControl, error) {
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Get(node.URL)
	if err != nil {
		return nil, fmt.Errorf("HTTP error on %s: %w", node.Name, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read error: %w", err)
	}

	var power RedfishPowerResponse
	if err := json.Unmarshal(body, &power); err != nil {
		return nil, fmt.Errorf("JSON parse error: %w", err)
	}

	if len(power.PowerControl) == 0 {
		return nil, fmt.Errorf("no PowerControl data for %s", node.Name)
	}

	return &power.PowerControl[0], nil
}

func appendCSV(path string, records [][]string) error {
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return err
	}
	defer f.Close()

	// Write header if file is empty
	info, _ := f.Stat()
	w := csv.NewWriter(f)
	if info.Size() == 0 {
		w.Write([]string{"node_name", "watts_consumed", "watts_average", "watts_max", "watts_min", "watts_capacity", "collected_at"})
	}
	w.WriteAll(records)
	return w.Error()
}

func collect(outPath string) {
	var records [][]string
	ts := time.Now().UTC().Format("2006-01-02 15:04:05")

	for _, node := range nodes {
		pc, err := fetchPower(node)
		if err != nil {
			log.Printf("[ERROR] %v", err)
			continue
		}
		records = append(records, []string{
			node.Name,
			strconv.FormatFloat(pc.PowerConsumedWatts, 'f', 2, 64),
			strconv.FormatFloat(pc.PowerMetrics.AverageConsumedWatts, 'f', 2, 64),
			strconv.FormatFloat(pc.PowerMetrics.MaxConsumedWatts, 'f', 2, 64),
			strconv.FormatFloat(pc.PowerMetrics.MinConsumedWatts, 'f', 2, 64),
			strconv.FormatFloat(pc.PowerCapacityWatts, 'f', 2, 64),
			ts,
		})
		log.Printf("[OK] %s → %.1fW (avg %.1fW)", node.Name, pc.PowerConsumedWatts, pc.PowerMetrics.AverageConsumedWatts)
	}

	if err := appendCSV(outPath, records); err != nil {
		log.Printf("[ERROR] CSV write failed: %v", err)
	}
}

func main() {
	outPath := "../data/raw_physical_nodes.csv"
	log.Println("PowerAudit Redfish collector started — polling every 60s")
	log.Printf("Output: %s", outPath)

	collect(outPath)

	ticker := time.NewTicker(60 * time.Second)
	for range ticker.C {
		collect(outPath)
	}
}
