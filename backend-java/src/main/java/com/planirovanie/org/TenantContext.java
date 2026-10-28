package com.planirovanie.org;

import java.util.function.Supplier;

/**
 * Current team (tenant) of the running request/thread. The value is the PHYSICAL schema the team's
 * data lives in; {@link #DEFAULT} means "the connection's default schema" (public), which holds the
 * first team and all platform tables (users, sessions, streams, teams, memberships).
 * Set by {@code AuthInterceptor} for team-scoped endpoints and cleared after the request.
 */
public final class TenantContext {
    public static final String DEFAULT = "_default";
    private static final ThreadLocal<String> CUR = new ThreadLocal<>();

    private TenantContext() {}

    public static String get() { String s = CUR.get(); return s == null ? DEFAULT : s; }
    public static void set(String schema) { if (schema == null || schema.isBlank()) CUR.remove(); else CUR.set(schema); }
    public static void clear() { CUR.remove(); }

    /** Runs {@code body} with the given schema as the current tenant, restoring the previous one.
     *  Callers must NOT be inside a transaction: the Hibernate session picks the tenant when it opens. */
    public static <T> T callAs(String schema, Supplier<T> body) {
        String prev = CUR.get();
        set(schema);
        try { return body.get(); } finally { if (prev == null) CUR.remove(); else CUR.set(prev); }
    }
}
