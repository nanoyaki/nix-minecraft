(ns test
  (:require [cheshire.core :as json])
  (:import [java.security MessageDigest]))

(defn sha256 [string]
  (let [digest (.digest (MessageDigest/getInstance "SHA-256") (.getBytes string "UTF-8"))]
    (apply str (map (partial format "%02x") digest))))

(defn neoforge?
  [lib]
  (re-matches #"^net.neoforged:neoforge:.*" lib))

(comment
  (sha256 "test")
  (->> (json/parse-string (slurp "loader_locks.json") true)
       (vals)
       (mapcat vals)
       (group-by (comp
                  sha256 json/generate-string (partial into (sorted-set))
                  (partial filter (comp not neoforge?))
                  :libraries))
       (keep (fn [[sha versions]]
               (when (> (count versions) 1)
                 [sha (into (sorted-set) (map :version versions))])))
       ; (sort-by (comp count second))
       (map (comp dec count second))
       (reduce + 0)))
