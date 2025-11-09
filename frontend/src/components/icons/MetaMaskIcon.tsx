import React from 'react';

export const MetaMaskIcon: React.FC<{ size?: number; className?: string }> = ({ size = 16, className }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 318.6 318.6"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
    focusable="false"
    preserveAspectRatio="xMidYMid meet"
    className={className}
    style={{ display: 'inline-block', verticalAlign: 'text-bottom' }}
  >
    <g stroke="currentColor" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none">
      <path d="m274.1 35.5-99.5 73.9L193 65.8z" />
      <path d="m44.4 35.5 98.7 74.6-17.5-44.3z" />
      <path d="m103.6 138.2-15.8 23.9 56.3 2.5-2-60.5z" />
      <path d="m214.9 138.2-39-34.8-1.3 61.2 56.2-2.5z" />
      <path d="M106.8 247.4l33.8-16.5-29.2-22.8zM177.9 230.9l33.9 16.5-4.7-39.3z" />
    </g>
  </svg>
);

export default MetaMaskIcon;
