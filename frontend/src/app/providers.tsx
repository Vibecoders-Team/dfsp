import { PropsWithChildren } from "react";

/**
 * Глобальные провайдеры приложения (Theme/Query/i18n и т.п. — потом докрутим).
 * Пока просто прокидывает children как есть.
 */
export default function Providers({ children }: PropsWithChildren) {
  return <>{children}</>;
}
