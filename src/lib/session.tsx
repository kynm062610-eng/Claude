import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { Session } from '@supabase/supabase-js';
import { supabase } from './supabase';
import type { Child } from '../types';

/**
 * この端末が「子どもの端末」か「保護者の端末」かを判定して保持する。
 *
 * 子どもは保護者のセッションにぶら下がらず、独自の匿名 auth ユーザーを持つ。
 * こうしないと保護者のセッションで子どものデータが常に読めてしまい、
 * 見まもりモード off が見せかけになる（詳細は docs/01-safety-and-privacy.md）。
 */
export type Role = 'child' | 'guardian' | null;

type SessionState = {
  loading: boolean;
  session: Session | null;
  role: Role;
  child: Child | null;
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children: node }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [session, setSession] = useState<Session | null>(null);
  const [role, setRole] = useState<Role>(null);
  const [child, setChild] = useState<Child | null>(null);

  const resolveRole = useCallback(async (current: Session | null) => {
    if (!current) {
      setRole(null);
      setChild(null);
      return;
    }

    const { data: childRow } = await supabase
      .from('children')
      .select('*')
      .eq('auth_user_id', current.user.id)
      .maybeSingle();

    if (childRow) {
      setChild(childRow as Child);
      setRole('child');
      return;
    }

    const { data: guardianRow } = await supabase
      .from('guardians')
      .select('id')
      .eq('id', current.user.id)
      .maybeSingle();

    setChild(null);
    setRole(guardianRow ? 'guardian' : null);
  }, []);

  const refresh = useCallback(async () => {
    const { data } = await supabase.auth.getSession();
    setSession(data.session);
    await resolveRole(data.session);
  }, [resolveRole]);

  useEffect(() => {
    let active = true;

    (async () => {
      await refresh();
      if (active) setLoading(false);
    })();

    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      void resolveRole(next);
    });

    return () => {
      active = false;
      sub.subscription.unsubscribe();
    };
  }, [refresh, resolveRole]);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
    setRole(null);
    setChild(null);
  }, []);

  const value = useMemo<SessionState>(
    () => ({ loading, session, role, child, refresh, signOut }),
    [loading, session, role, child, refresh, signOut],
  );

  return <SessionContext.Provider value={value}>{node}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession は SessionProvider の内側で使ってください');
  return ctx;
}

/** 子どもセッション前提の画面で使う。プロフィール未取得なら null を返す。 */
export function useChild(): Child | null {
  return useSession().child;
}
