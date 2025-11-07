import React from 'react';

// Simplified WalletConnect glyph
export const WalletConnectIcon: React.FC<{ size?: number; className?: string }> = ({ size = 18, className }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 1200 675"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
    focusable="false"
    className={className}
  >
    <path d="M477 252c79-76 207-76 286 0l9 8 9-8c79-76 207-76 286 0l73 70c6 5 6 14 0 20l-124 119c-5 5-13 5-18 0l-84-81c-4-4-10-4-14 0l-84 81c-5 5-13 5-18 0l-84-81c-4-4-10-4-14 0l-84 81c-5 5-13 5-18 0L404 342c-6-6-6-15 0-20z" fill="#3b99fc"/>
  </svg>
);

export default WalletConnectIcon;

