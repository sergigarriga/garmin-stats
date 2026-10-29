import DirectionsRun from '@mui/icons-material/DirectionsRun';
import DirectionsBike from '@mui/icons-material/DirectionsBike';
import Pool from '@mui/icons-material/Pool';
import FitnessCenter from '@mui/icons-material/FitnessCenter';
import DirectionsWalk from '@mui/icons-material/DirectionsWalk';
import Treadmill from '@mui/icons-material/DirectionsRunOutlined';
import SportsGymnastics from '@mui/icons-material/SportsGymnastics';

export function SportIcon({ group }: { group: string }) {
  switch (group) {
    case 'Correr': return <DirectionsRun />;
    case 'Cinta': return <Treadmill />;
    case 'Bici': return <DirectionsBike />;
    case 'Natación': return <Pool />;
    case 'Fuerza': return <FitnessCenter />;
    case 'Caminar': return <DirectionsWalk />;
    default: return <SportsGymnastics />;
  }
}
