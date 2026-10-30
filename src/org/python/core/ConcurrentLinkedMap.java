package org.python.core;

import java.util.AbstractMap;
import java.util.AbstractSet;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentMap;

/** Insertion-ordered, synchronized map for native Python 3 dictionaries.
 * Iterators snapshot keys, retain live values, and remove from the backing map.
 * As with ConcurrentHashMap, null keys and values are not supported.
 */
final class ConcurrentLinkedMap<K, V> extends AbstractMap<K, V> implements ConcurrentMap<K, V> {
    private final LinkedHashMap<K, V> data = new LinkedHashMap<K, V>();

    @Override public synchronized int size() { return data.size(); }
    @Override public synchronized boolean containsKey(Object key) { return data.containsKey(key); }
    @Override public synchronized boolean containsValue(Object value) { return data.containsValue(value); }
    @Override public synchronized V get(Object key) { return data.get(key); }
    @Override public synchronized V put(K key, V value) {
        return data.put(Objects.requireNonNull(key), Objects.requireNonNull(value));
    }
    @Override public synchronized V remove(Object key) { return data.remove(key); }
    @Override public synchronized void clear() { data.clear(); }
    @Override public synchronized V putIfAbsent(K key, V value) {
        Objects.requireNonNull(key);
        Objects.requireNonNull(value);
        V previous = data.get(key);
        if (previous == null) data.put(key, value);
        return previous;
    }
    @Override public synchronized boolean remove(Object key, Object value) {
        Objects.requireNonNull(value);
        if (!value.equals(data.get(key))) return false;
        data.remove(key);
        return true;
    }
    @Override public synchronized boolean replace(K key, V oldValue, V newValue) {
        Objects.requireNonNull(oldValue);
        Objects.requireNonNull(newValue);
        if (!oldValue.equals(data.get(key))) return false;
        data.put(key, newValue);
        return true;
    }
    @Override public synchronized V replace(K key, V value) {
        Objects.requireNonNull(value);
        if (!data.containsKey(key)) return null;
        return data.put(key, value);
    }

    @Override public Set<Map.Entry<K, V>> entrySet() {
        return new AbstractSet<Map.Entry<K, V>>() {
            @Override public int size() { return ConcurrentLinkedMap.this.size(); }
            @Override public void clear() { ConcurrentLinkedMap.this.clear(); }
            @Override public boolean contains(Object candidate) {
                if (!(candidate instanceof Map.Entry)) return false;
                Map.Entry<?, ?> entry = (Map.Entry<?, ?>)candidate;
                Object value = get(entry.getKey());
                return value != null && value.equals(entry.getValue());
            }
            @Override public boolean remove(Object candidate) {
                if (!(candidate instanceof Map.Entry)) return false;
                Map.Entry<?, ?> entry = (Map.Entry<?, ?>)candidate;
                return ConcurrentLinkedMap.this.remove(entry.getKey(), entry.getValue());
            }
            @Override public Iterator<Map.Entry<K, V>> iterator() {
                final Iterator<K> keys;
                synchronized (ConcurrentLinkedMap.this) {
                    keys = new ArrayList<K>(data.keySet()).iterator();
                }
                return new Iterator<Map.Entry<K, V>>() {
                    private K current;
                    private boolean removable;
                    @Override public boolean hasNext() { return keys.hasNext(); }
                    @Override public Map.Entry<K, V> next() {
                        if (!keys.hasNext()) throw new NoSuchElementException();
                        final K key = keys.next();
                        current = key;
                        removable = true;
                        return new SimpleEntry<K, V>(key, get(key)) {
                            @Override public V getValue() { return get(key); }
                            @Override public V setValue(V value) {
                                V old = put(key, value);
                                super.setValue(value);
                                return old;
                            }
                        };
                    }
                    @Override public void remove() {
                        if (!removable) throw new IllegalStateException();
                        ConcurrentLinkedMap.this.remove(current);
                        removable = false;
                    }
                };
            }
        };
    }
}
