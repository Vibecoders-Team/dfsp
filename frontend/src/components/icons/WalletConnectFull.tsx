import React from 'react';
import WcSvg from '@/assets/icons/WalletConnect-Logo.svg';

export const WalletConnectFull: React.FC<{ size?: number; className?: string; alt?: string }> = ({
                                                                                                     size = 18,
                                                                                                     className = '',
                                                                                                     alt = 'WalletConnect'
                                                                                                 }) => (
    <img src={WcSvg} width={size} height={size} alt={alt} className={className}
         style={{display: 'inline-block', verticalAlign: 'text-bottom'}}/>
);

export default WalletConnectFull;
