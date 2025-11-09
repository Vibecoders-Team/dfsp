import React from 'react';
import MetaMaskSvg from '@/assets/icons/MetaMask-Logo.svg';

export const MetaMaskFull: React.FC<{ size?: number; className?: string; alt?: string }> = ({ size = 18, className = '', alt = 'MetaMask' }) => (
  <img src={MetaMaskSvg} width={size} height={size} alt={alt} className={className} style={{ display: 'inline-block', verticalAlign: 'text-bottom' }} />
);

export default MetaMaskFull;
